"""Meta Ad Library probe: one search, one network arm, and what came back."""
import asyncio
import collections
import time
from urllib.parse import urlsplit

from apify import Actor
from meta_ads_collector import (ERROR_OCCURRED, PAGE_FETCHED, RATE_LIMITED, SESSION_REFRESHED, MetaAdsCollector)


async def proxy_url(arm: str) -> str | None:
    if arm == 'none':
        return None
    cfg = await Actor.create_proxy_configuration(groups=['RESIDENTIAL'] if arm == 'residential' else None)
    url = await cfg.new_url(f'meta{int(time.time())}') if cfg else None
    if not url:
        return None
    # meta-ads-collector takes one proxy as host:port:user:pass and splits it on ':', so Apify's
    # http://user:pass@host:port has to be converted or it is mangled into an invalid address.
    u = urlsplit(url)
    return f'{u.hostname}:{u.port}:{u.username}:{u.password}'


def collect(query: str, page_id: str, country: str, max_ads: int, proxy: str | None, events: collections.Counter):
    def on(name):
        return lambda *a, **k: events.update([name])
    callbacks = {e: on(e) for e in (PAGE_FETCHED, RATE_LIMITED, ERROR_OCCURRED, SESSION_REFRESHED)}
    c = MetaAdsCollector(proxy=proxy, rate_limit_delay=2.0, callbacks=callbacks)
    if page_id:
        return c.collect(country=country, search_type='PAGE', page_ids=[page_id], max_results=max_ads, page_size=30)
    return c.collect(query=query, country=country, max_results=max_ads, page_size=30)


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}
        arm = inp.get('proxy', 'none')
        events: collections.Counter = collections.Counter()
        out = {'input': inp, 'arm': arm}
        t0 = time.time()
        try:
            url = await proxy_url(arm)
            ads = await asyncio.to_thread(collect, inp.get('query', 'nike'), inp.get('pageId', ''),
                                          inp.get('country', 'US'), int(inp.get('maxAds', 300)), url, events)
            out.update(status='ok', ads=len(ads), uniqueAds=len({a.id for a in ads}))
            rows = []
            for a in ads[:5]:
                d = a.to_dict()
                d['creatives'] = (d.get('creatives') or [])[:2]
                rows.append(d)
            await Actor.push_data(rows)
        except Exception as exc:  # noqa: BLE001  a probe records failures
            out.update(status='error', error=f'{type(exc).__name__}: {str(exc)[:400]}')
        out.update(seconds=round(time.time() - t0, 1), events=dict(events))
        await Actor.set_value('OUTPUT', out)
        Actor.log.info(f'probe result: {out}')


if __name__ == '__main__':
    asyncio.run(main())
