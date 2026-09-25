import asyncio
import logging
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from meta_ads_collector.models import PageSearchResult

from src import main, meta
from src.inputs import parse_input
from tests.test_rows import make_ad


class FakeClient:
    """script: list of outcomes per session: a list of ads, or an exception, or 'blocked' (0 ads + rate limit)."""

    def __init__(self, script, events, pages=None):
        self.script, self.events, self.pages = script, events, pages or []

    def search(self, **kw):
        outcome = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if outcome == 'blocked':
            self.events.update(['rate_limited'])
            return iter(())
        if isinstance(outcome, Exception):
            def boom():
                raise outcome
                yield  # makes this a generator
            return boom()
        return iter(outcome)

    def search_pages(self, name, country='US'):
        return self.pages


class FakeSessions:
    def __init__(self, script, pages=None):
        self.script, self.pages, self.opened = script, pages, 0

    async def new(self):
        self.opened += 1
        s = meta.Session.__new__(meta.Session)
        import collections
        s.events = collections.Counter()
        s.client = FakeClient(self.script, s.events, self.pages)
        return s


class FakeActor:
    def __init__(self, ppe=True, budget=None, price=0.0007):
        self.ppe, self.budget, self.price, self.rows, self.spent = ppe, budget, price, [], 0.0

    def get_charging_manager(self):
        return SimpleNamespace(get_pricing_info=lambda: SimpleNamespace(is_pay_per_event=self.ppe))

    async def push_data(self, rows, *, charged_event_name=None):
        n = len(rows)
        if self.budget is not None:
            n = min(n, int(round((self.budget - self.spent) / self.price, 6)))
        self.rows += rows[:n]
        self.spent += n * self.price
        return SimpleNamespace(charged_count=n, event_charge_limit_reached=self.budget is not None and n < len(rows))


class Quiet:
    log = logging.getLogger('meta-test')
    log.addHandler(logging.NullHandler())
    log.propagate = False
    configuration = None

    async def set_value(self, *a, **k):
        pass

    async def set_status_message(self, *a, **k):
        pass


def ads(n, start=0, **kw):
    return [make_ad(i=str(start + i), page=(f'p{(start + i) % 4}', f'Page {(start + i) % 4}', 5000), **kw) for i in range(n)]


class RunTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sdk = Quiet()
        p = mock.patch.object(main, 'Actor', self.sdk)
        p.start()
        self.addCleanup(p.stop)

    async def run_it(self, raw, script, *, budget=None, pages=None):
        actor = FakeActor(budget=budget)
        run = main.Run(parse_input(raw), main.Delivery(actor), FakeSessions(script, pages))
        await run.execute()
        return run, actor

    async def test_max_ads_is_respected_and_charged(self):
        run, actor = await self.run_it({'searchTerms': ['shoes'], 'maxAds': 25}, [ads(60)])
        self.assertEqual((len(actor.rows), run.delivery.charged['ad']), (25, 25))

    async def test_spending_limit_stops_cleanly(self):
        run, actor = await self.run_it({'searchTerms': ['shoes'], 'maxAds': 100}, [ads(60)], budget=0.0105)
        self.assertEqual(len(actor.rows), 15)
        self.assertEqual(run.stop, 'limit')

    async def test_error_rotates_to_a_fresh_ip_and_skips_seen_ads(self):
        run, actor = await self.run_it({'searchTerms': ['shoes'], 'maxAds': 20}, [RuntimeError('curl 56'), ads(20)])
        self.assertEqual(len(actor.rows), 20)
        self.assertEqual(run.searches[0]['sessions'], 2)

    async def test_blocked_everywhere_fails_and_costs_nothing(self):
        run, actor = await self.run_it({'searchTerms': ['shoes']}, ['blocked'])
        self.assertEqual((len(actor.rows), run.searches[0]['status'], run.failed()), (0, 'failed', True))
        self.assertEqual(run.searches[0]['sessions'], 1 + meta.MAX_ROTATIONS)

    async def test_no_results_is_a_valid_answer(self):
        run, actor = await self.run_it({'searchTerms': ['zzqx']}, [[]])
        self.assertEqual((run.searches[0]['status'], run.failed()), ('done', False))

    async def test_min_days_and_version_grouping(self):
        old = [make_ad(i=str(i), start=datetime(2026, 6, 1)) for i in range(5)]
        fresh = [make_ad(i=str(10 + i), start=datetime(2026, 9, 24)) for i in range(5)]
        run, actor = await self.run_it({'searchTerms': ['s'], 'minDaysRunning': 30}, [old + fresh])
        self.assertEqual(len(actor.rows), 5)
        self.assertTrue(all(r['daysRunning'] >= 30 for r in actor.rows))
        run, actor = await self.run_it({'searchTerms': ['s'], 'groupVersions': True},
                                       [[make_ad(i='a'), make_ad(i='b')]])
        self.assertEqual(len(actor.rows), 2)                 # different version groups (ga, gb)

    async def test_advertisers_mode_charges_per_advertiser(self):
        run, actor = await self.run_it({'mode': 'advertisers', 'searchTerms': ['yoga'], 'maxAds': 40}, [ads(40)])
        self.assertEqual(len(actor.rows), 4)                 # pages p0..p3
        self.assertEqual(run.delivery.charged['advertiser'], 4)

    async def test_impersonation_skips_the_official_page(self):
        pages = [PageSearchResult(page_id='p0', page_name='Page 0', page_verified=True)]
        run, actor = await self.run_it({'mode': 'impersonation', 'searchTerms': ['Page 0'], 'maxAds': 50},
                                       [ads(8)], pages=pages)
        self.assertEqual(run.official_ids, {'p0'})
        self.assertTrue(actor.rows and all(r['pageId'] != 'p0' for r in actor.rows))
        self.assertTrue(all(r['impersonation'] for r in actor.rows))

    async def test_pages_mode_resolves_a_name(self):
        pages = [PageSearchResult(page_id='777', page_name='Gymshark')]
        run, actor = await self.run_it({'mode': 'pages', 'pages': ['Gymshark'], 'maxAds': 5}, [ads(9)], pages=pages)
        self.assertEqual((run.searches[0]['pageId'], len(actor.rows)), ('777', 5))


if __name__ == '__main__':
    asyncio.run(unittest.main())


class Worldwide(unittest.TestCase):
    def test_all_passes_the_library_check_and_codes_still_do(self):
        c = meta.WorldwideCollector.__new__(meta.WorldwideCollector)
        c._validate_params('ALL', 'ACTIVE', 'KEYWORD_UNORDERED', None, 'ALL')      # no exception
        c._validate_params('ALL', 'ACTIVE', 'KEYWORD_UNORDERED', None, 'IN')
        with self.assertRaises(meta.InvalidParameterError):
            c._validate_params('ALL', 'ACTIVE', 'KEYWORD_UNORDERED', None, 'INDIA')


class InputErrors(RunTests):
    async def test_refused_settings_are_not_retried_or_called_a_block(self):
        run, actor = await self.run_it({'searchTerms': ['shoes']}, [meta.InvalidParameterError('country', 'X', 'a code')])
        s = run.searches[0]
        self.assertEqual((s['sessions'], s['status']), (1, 'failed'))
        self.assertIn('refused', s['reason'])
        self.assertNotIn('blocked', run.message(True))
