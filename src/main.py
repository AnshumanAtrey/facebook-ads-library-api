"""
Facebook Ads Library Scraper API: the public Meta Ad Library as rows, with no login or cookies.

Four report types: ads for keywords, ads of given advertisers (pages), the advertisers behind a
keyword (a lead list of pages spending on ads now), and a brand scam check (ads that use a brand's
name from pages that are not the brand's own, with the signals that make them look off).

- Every search runs on its own Apify residential IP (Meta rate-limits Apify's own IPs and the
  datacenter proxy to 0 ads). A search Meta blocks starts over on a fresh IP, at most twice.
- Up to 3 searches run at once. Rows are pushed and charged in small batches as they arrive; a
  spending limit stops the run between batches and every row already delivered is kept.
- A run where every search finished but found nothing is a valid answer (no scam ads is good
  news), so it SUCCEEDS with 0 rows; a run that delivered nothing because Meta blocked it FAILS.
- The run summary is the OUTPUT record, refreshed about every 10 s (each key-value write is billed).
- The status message goes through a wrapper: SDK 3.x validates the run object against an enum that
  lacks the APIFY_AI run origin and raises after the message is stored.
"""
import asyncio
import time
from collections import Counter
from datetime import datetime, timezone

from apify import Actor

from . import meta
from .inputs import Config, InputError, parse_input
from .rows import _fold, ad_row, advertiser_rows, domain_of, impersonation, matches_media

AD_EVENT = 'ad'                 # pay-per-event: one ad row; must equal the event key in .actor/store.json
ADVERTISER_EVENT = 'advertiser'  # pay-per-event: one advertiser row (advertisers mode)
PARALLEL = 3                    # searches at once, each on its own residential IP
PUSH_BATCH = 10
OUTPUT_EVERY_S = 10
STATUS_EVERY_S = 5
MARGIN_S = 60                   # stop starting work this long before the run's timeout
OFFICIAL_SAMPLE = 20            # ads read from each official page to learn its real landing domains
STOP_REASONS = {'limit': 'your spending limit for this run was reached. Raise the limit to get the rest.',
                'time': 'the run was about to reach its time limit. Raise the run timeout to get the rest.'}


async def safe_status(message: str) -> None:
    try:
        await Actor.set_status_message(message[:500])
    except Exception as exc:  # noqa: BLE001
        Actor.log.debug(f'status message stored but not confirmed by the SDK: {exc}')


def seconds_left_in_run() -> float | None:
    config = getattr(Actor, 'configuration', None) or getattr(Actor, 'config', None)
    timeout_at = getattr(config, 'timeout_at', None) if config else None
    if not timeout_at:
        return None
    return (timeout_at - datetime.now(timezone.utc)).total_seconds()


class Delivery:
    """Pushes rows charged as an event, counts what was charged and notices the spending limit."""

    def __init__(self, actor=Actor):
        self.actor = actor
        info = actor.get_charging_manager().get_pricing_info()
        self.ppe = info.is_pay_per_event
        self.charged: Counter = Counter({AD_EVENT: 0, ADVERTISER_EVENT: 0})
        self.rows = 0
        self.limit = False

    async def push(self, rows: list[dict], event: str) -> int:
        """Returns how many rows were delivered: the SDK drops rows the spending limit cannot pay for."""
        if not rows:
            return 0
        result = await self.actor.push_data(rows, charged_event_name=event)
        done = result.charged_count if self.ppe else len(rows)
        if self.ppe and (result.event_charge_limit_reached or done < len(rows)):
            self.limit = True
        self.charged[event] += done
        self.rows += done
        return done


class Run:
    def __init__(self, cfg: Config, delivery: Delivery, sessions: meta.Sessions, clock=time.monotonic):
        self.cfg, self.delivery, self.sessions, self.clock = cfg, delivery, sessions, clock
        self.t0 = clock()
        self.stop: str | None = None
        self.searches: list[dict] = []
        self.seen_ads: set[str] = set()
        self.seen_groups: set[str] = set()
        self.seen_pages: set[str] = set()
        self.official_ids: set[str] = set()
        self.official_domains: set[str] = set()
        self.official_names: list[str] = []
        self.last_output = 0.0
        self.last_status = 0.0
        self.risk: Counter = Counter()           # brand scam check: delivered rows by risk level

    # ---------------------------------------------------------------- time --
    def time_ok(self) -> bool:
        left = seconds_left_in_run()
        if left is not None and left < MARGIN_S:
            self.stop = self.stop or 'time'
            return False
        return True

    # ------------------------------------------------------------- fetching --
    def new_search(self, label: str, term: str | None, page_id: str | None) -> dict:
        s = {'search': label, 'term': term, 'pageId': page_id, 'status': 'waiting', 'reason': None,
             'adsScanned': 0, 'saved': 0, 'officialSkipped': 0, 'sessions': 0, 'problem': None}
        self.searches.append(s)
        return s

    async def fetch(self, s: dict, want_raw: int | None = None):
        """Async generator of Meta Ad objects for one search, new ads only, rotating residential IPs
        when Meta blocks the session or the library errors. want_raw caps ads read (advertisers mode)."""
        seen: set[str] = set()
        for rotation in range(meta.MAX_ROTATIONS + 1):
            session = await self.sessions.new()
            s['sessions'] += 1
            problem = None
            got = 0
            try:
                gen = session.client.search(**meta.search_kwargs(self.cfg, s['term'], s['pageId'], None))
                while True:
                    ad = await asyncio.to_thread(next, gen, None)
                    if ad is None:
                        break
                    got += 1
                    s['adsScanned'] += 1
                    if ad.id in seen:
                        continue
                    seen.add(ad.id)
                    yield ad
                    if self.stop or not self.time_ok() or (want_raw and len(seen) >= want_raw):
                        return
            except meta.InvalidParameterError as exc:   # our input, not Meta blocking: a new IP will not help
                s['problem'], s['inputError'] = f'{exc}'[:200], True
                return
            except Exception as exc:  # noqa: BLE001  the library raises many kinds; each one means a new IP
                problem = f'{type(exc).__name__}: {str(exc)[:160]}'
            if problem is None and not (got == 0 and session.blocked):
                return
            problem = problem or 'Meta rate-limited the connection'
            if rotation == meta.MAX_ROTATIONS or not self.time_ok():
                s['problem'] = problem
                return
            Actor.log.warning(f'[{s["search"]}] {problem}; retrying on a fresh residential IP '
                              f'({rotation + 1}/{meta.MAX_ROTATIONS}).')

    def keep(self, row: dict) -> bool:
        cfg = self.cfg
        if row['adId'] in self.seen_ads:
            return False
        if cfg.min_days and (row['daysRunning'] is None or row['daysRunning'] < cfg.min_days):
            return False
        if not matches_media(row, cfg.media_type):
            return False
        if cfg.group_versions and row['versionGroupId']:
            if row['versionGroupId'] in self.seen_groups:
                return False
            self.seen_groups.add(row['versionGroupId'])
        self.seen_ads.add(row['adId'])
        return True

    # ---------------------------------------------------------------- units --
    async def ads_search(self, s: dict) -> None:
        cfg, batch, saved = self.cfg, [], 0
        s['status'] = 'running'
        async for ad in self.fetch(s):
            row = ad_row(ad, s['term'] or s['search'], cfg.country)
            if cfg.mode == 'impersonation':
                check = impersonation(row, cfg.terms[0], self.official_ids, self.official_domains)
                if check is None:
                    s['officialSkipped'] += 1
                    continue
                row['impersonation'] = check
            if not self.keep(row):
                continue
            batch.append(row)
            if len(batch) >= PUSH_BATCH or saved + len(batch) >= cfg.max_ads:
                saved += await self.deliver(batch[:cfg.max_ads - saved])
                batch = []
                await self.report()
                if self.delivery.limit:
                    self.stop = 'limit'
                    break
                if saved >= cfg.max_ads:
                    break
        if batch and not self.delivery.limit and saved < cfg.max_ads:
            saved += await self.deliver(batch[:cfg.max_ads - saved])
            if self.delivery.limit:
                self.stop = 'limit'
        self.finish(s, saved)

    async def deliver(self, rows: list[dict]) -> int:
        done = await self.delivery.push(rows, AD_EVENT)
        self.risk.update(r['impersonation']['risk'] for r in rows[:done] if r['impersonation'])
        return done

    async def advertisers_search(self, s: dict) -> None:
        s['status'] = 'running'
        rows = []
        async for ad in self.fetch(s, want_raw=self.cfg.max_ads):
            row = ad_row(ad, s['term'], self.cfg.country)
            if self.keep(row):
                rows.append(row)
        found = [a for a in advertiser_rows(rows, s['term'], self.cfg.country) if a['pageId'] not in self.seen_pages]
        saved = 0
        for i in range(0, len(found), PUSH_BATCH):
            if self.delivery.limit:
                break
            chunk = found[i:i + PUSH_BATCH]
            done = await self.delivery.push(chunk, ADVERTISER_EVENT)
            self.seen_pages.update(a['pageId'] for a in chunk[:done])
            saved += done
            if self.delivery.limit:
                self.stop = 'limit'
        self.finish(s, saved)

    def finish(self, s: dict, saved: int) -> None:
        s['saved'] = saved
        if s.get('inputError'):
            s['status'], s['reason'] = 'failed', f'Meta refused the search settings: {s["problem"]}'
        elif s['problem'] and not saved:
            s['status'], s['reason'] = 'failed', f'Meta blocked this search even on fresh IPs ({s["problem"]}).'
        elif s['problem']:
            s['status'], s['reason'] = 'partial', f'Saved {saved}, then Meta blocked the search ({s["problem"]}).'
        elif self.stop and saved < self.cfg.max_ads:
            s['status'], s['reason'] = 'partial', f'Stopped early: {STOP_REASONS[self.stop]}'
        else:
            s['status'] = 'done'
            s['reason'] = None if saved else 'Meta has no ads that match this search and these filters.'

    # ------------------------------------------------------ page resolution --
    async def resolve(self, ref: str) -> tuple[str | None, str]:
        """A page id stays; a name or vanity handle is looked up. Returns (id, label)."""
        if ref.isdigit():
            return ref, ref
        session = await self.sessions.new()
        try:
            found = await asyncio.to_thread(meta.resolve_pages, session, ref, self.cfg.country)
        except Exception as exc:  # noqa: BLE001
            Actor.log.warning(f'Could not look up the advertiser "{ref}": {type(exc).__name__}: {str(exc)[:120]}')
            return None, ref
        if not found:
            return None, ref
        want = _fold(ref)
        best = next((p for p in found if _fold(p.page_name) == want or _fold(p.page_alias or '') == want), found[0])
        return best.page_id, f'{best.page_name} ({best.page_id})'

    async def setup_official(self) -> None:
        brand = self.cfg.terms[0]
        refs = self.cfg.official
        if refs:
            for ref in refs:
                pid, label = await self.resolve(ref)
                if pid:
                    self.official_ids.add(pid)
                    self.official_names.append(label)
                else:
                    self.cfg.notes.append(f'Could not find the official page "{ref}"; it was left out.')
        else:
            session = await self.sessions.new()
            try:
                found = await asyncio.to_thread(meta.resolve_pages, session, brand, self.cfg.country)
            except Exception as exc:  # noqa: BLE001
                found = []
                Actor.log.warning(f'Could not look up the brand\'s pages: {type(exc).__name__}: {str(exc)[:120]}')
            b = _fold(brand)
            mine = [p for p in found if _fold(p.page_name) == b or (p.page_verified and b in _fold(p.page_name))]
            for p in mine[:5]:
                self.official_ids.add(p.page_id)
                self.official_names.append(f'{p.page_name} ({p.page_id})')
            self.cfg.notes.append(
                'Treated these as the brand\'s own pages: ' + ', '.join(self.official_names) +
                '. Add them in Official pages (officialPages) to be exact.' if self.official_names else
                'Found no official page for the brand, so every page using it is listed. Add the brand\'s page in '
                'Official pages (officialPages) to skip its own ads.')
        for pid in list(self.official_ids):
            s = {'search': f'official page {pid}', 'term': None, 'pageId': pid, 'adsScanned': 0, 'sessions': 0,
                 'problem': None}
            async for ad in self.fetch(s, want_raw=OFFICIAL_SAMPLE):
                d = domain_of(next((c.link_url for c in ad.creatives or [] if c.link_url), None))
                if d:
                    self.official_domains.add(d)

    # --------------------------------------------------------------- report --
    def message(self, final: bool) -> str:
        cfg = self.cfg
        what = 'advertisers' if cfg.mode == 'advertisers' else 'ads'
        saved = self.delivery.rows
        done = sum(s['status'] in ('done', 'partial', 'failed') for s in self.searches)
        parts = [f'Saved {saved} {what} from {done} of {len(self.searches)} searches'
                 + (f' ({"worldwide" if cfg.country == "ALL" else cfg.country}).' if final else '...')]
        if cfg.mode == 'impersonation' and final:
            parts.append(f'Brand "{cfg.terms[0]}": {self.risk["high"]} high-risk, {self.risk["medium"]} medium and '
                         f'{self.risk["low"]} low-risk ads from other pages; '
                         f'{sum(s["officialSkipped"] for s in self.searches)} ads from the official pages skipped.')
        blocked = [s for s in self.searches if s['status'] == 'failed' and not s.get('inputError')]
        refused = [s for s in self.searches if s.get('inputError')]
        if blocked and final:
            parts.append(f'{len(blocked)} search(es) were blocked by Meta: run again later.')
        if refused and final:
            parts.append(f'{len(refused)} search(es) had settings Meta refused: {refused[0]["reason"]}')
        if self.stop and final:
            parts.append(f'The run stopped early because {STOP_REASONS[self.stop]}')
        return ' '.join(parts)

    def output(self, status: str) -> dict:
        return {
            'status': status,
            'message': self.message(status != 'running'),
            'notes': self.cfg.notes,
            'mode': self.cfg.mode,
            'country': self.cfg.country,
            'stopReason': self.stop,
            'searches': [{k: v for k, v in s.items() if k != 'term'} for s in self.searches],
            'rowsSaved': self.delivery.rows,
            'chargedEvents': dict(self.delivery.charged),
            'payPerEvent': self.delivery.ppe,
            'officialPages': self.official_names if self.cfg.mode == 'impersonation' else None,
            'officialDomains': sorted(self.official_domains) if self.cfg.mode == 'impersonation' else None,
            'riskCounts': dict(self.risk) if self.cfg.mode == 'impersonation' else None,
            'residentialSessions': self.sessions.opened,
            'elapsedSecs': round(self.clock() - self.t0, 1),
        }

    async def report(self, final: bool = False) -> None:
        now = self.clock()
        if final or now - self.last_status >= STATUS_EVERY_S:
            self.last_status = now
            await safe_status(self.message(final))
        if final or now - self.last_output >= OUTPUT_EVERY_S:
            self.last_output = now
            status = 'running' if not final else ('failed' if self.failed() else 'succeeded')
            await Actor.set_value('OUTPUT', self.output(status))

    def failed(self) -> bool:
        return not self.delivery.rows and any(s['status'] == 'failed' for s in self.searches)

    # ----------------------------------------------------------------- run --
    async def execute(self) -> None:
        cfg = self.cfg
        if cfg.mode == 'impersonation':
            await self.setup_official()
        if cfg.mode == 'pages':
            for ref in cfg.pages:
                pid, label = await self.resolve(ref)
                if pid:
                    self.new_search(label, None, pid)
                else:
                    s = self.new_search(ref, None, None)
                    s.update(status='failed', reason='No Facebook page found for this name or link.')
        else:
            for t in cfg.terms:
                self.new_search(t, t, None)
        work = [s for s in self.searches if s['status'] == 'waiting']
        handler = self.advertisers_search if cfg.mode == 'advertisers' else self.ads_search
        gate = asyncio.Semaphore(PARALLEL)

        async def one(s: dict) -> None:
            async with gate:
                if self.stop or not self.time_ok():
                    s.update(status='skipped', reason=f'Not started: {STOP_REASONS[self.stop or "time"]}')
                    return
                try:
                    await handler(s)
                except Exception as exc:  # noqa: BLE001  one search must never crash the run
                    Actor.log.exception(f'[{s["search"]}] unexpected error')
                    s.update(status='failed', reason=f'Unexpected error ({type(exc).__name__}): please report it.')

        await asyncio.gather(*(one(s) for s in work))


async def main() -> None:
    async with Actor:
        try:
            cfg = parse_input(await Actor.get_input())
        except InputError as exc:
            await Actor.set_value('OUTPUT', {'status': 'failed', 'message': str(exc)})
            await Actor.fail(status_message=str(exc))
            return
        for note in cfg.notes:
            Actor.log.warning(note)
        try:
            proxy_cfg = await Actor.create_proxy_configuration(groups=['RESIDENTIAL'])
        except Exception as exc:  # noqa: BLE001  local runs have no Apify Proxy
            Actor.log.warning(f'Residential proxy not available ({type(exc).__name__}); running on this machine\'s '
                              f'own IP, which Meta blocks on cloud servers.')
            proxy_cfg = None
        delivery = Delivery()
        Actor.log.info(f'Facebook Ads Library Scraper API: mode={cfg.mode} searches={len(cfg.terms) or len(cfg.pages)} '
                       f'country={cfg.country} status={cfg.status} maxAds={cfg.max_ads} payPerEvent={delivery.ppe}')
        run = Run(cfg, delivery, meta.Sessions(proxy_cfg))
        await run.execute()
        message = run.message(True)
        Actor.log.info(message)
        await run.report(final=True)
        if run.failed():
            await Actor.fail(status_message=message[:500])


if __name__ == '__main__':
    asyncio.run(main())
