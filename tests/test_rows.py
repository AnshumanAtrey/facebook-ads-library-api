import unittest
from datetime import datetime

from meta_ads_collector.models import Ad, AdCreative, PageInfo

from src.rows import ad_row, advertiser_rows, domain_of, impersonation

NOW = datetime(2026, 9, 25)


def make_ad(i='1', page=('p1', 'Shoe Shop', 5000), start=datetime(2026, 6, 1), stop=None, text='Buy Nike shoes',
            link='https://www.shoeshop.com/sale', video=None, images=('https://img/1.jpg',), cards=1, versions=3):
    creatives = [AdCreative(body=text, title='Sale', link_url=link, image_url=images[0] if images else None,
                            video_hd_url=video, cta_text='Shop now', cta_type='SHOP_NOW') for _ in range(cards)]
    return Ad(id=i, page=PageInfo(id=page[0], name=page[1], likes=page[2]), is_active=stop is None,
              delivery_start_time=start, delivery_stop_time=stop, creatives=creatives,
              publisher_platforms=['facebook', 'instagram'], collation_count=versions, collation_id='g' + i)


class Row(unittest.TestCase):
    def test_signals(self):
        r = ad_row(make_ad(), 'nike', 'US', NOW)
        self.assertEqual((r['daysRunning'], r['versions'], r['landingDomain'], r['callToAction'], r['platforms']),
                         (116, 3, 'shoeshop.com', 'Shop now', ['facebook', 'instagram']))
        self.assertEqual(r['adLibraryUrl'], 'https://www.facebook.com/ads/library/?id=1')
        self.assertIsNone(r['pageVerified'])            # Meta's ad search never says; unknown is None
        self.assertEqual(r['cards'], [])

    def test_carousel_cards(self):
        self.assertEqual(len(ad_row(make_ad(cards=3), None, 'US', NOW)['cards']), 3)

    def test_facebook_redirect_is_unwrapped(self):
        self.assertEqual(domain_of('https://l.facebook.com/l.php?u=https%3A%2F%2Fwww.example.org%2Fx&h=1'), 'example.org')

    def test_every_declared_field_is_present(self):
        from src.rows import AD_FIELDS
        self.assertEqual(set(ad_row(make_ad(), 'x', 'US', NOW)), set(AD_FIELDS))


class Impersonation(unittest.TestCase):
    def test_official_page_is_skipped(self):
        r = ad_row(make_ad(page=('nike1', 'Nike', 10_000_000)), 'Nike', 'US', NOW)
        self.assertIsNone(impersonation(r, 'Nike', {'nike1'}, {'nike.com'}))

    def test_lookalike_page_and_domain_new_ad_is_high(self):
        r = ad_row(make_ad(page=('x9', 'Nike Outlet Store', 120), start=datetime(2026, 9, 22),
                           link='https://nike-outlet-sale.shop/x'), 'Nike', 'US', NOW)
        got = impersonation(r, 'Nike', {'nike1'}, {'nike.com'})
        self.assertEqual(got['risk'], 'high')
        self.assertTrue(any('look-alike' in s for s in got['signals']))

    def test_reseller_is_low(self):
        r = ad_row(make_ad(page=('fl', 'Foot Locker', 3_000_000), link='https://www.footlocker.com/x'), 'Nike', 'US', NOW)
        self.assertEqual(impersonation(r, 'Nike', {'nike1'}, {'nike.com'})['risk'], 'low')


class Advertisers(unittest.TestCase):
    def test_one_row_per_page(self):
        rows = [ad_row(make_ad(i=str(i), page=('p1' if i < 3 else 'p2', 'A' if i < 3 else 'B', 10)), 'yoga', 'US', NOW)
                for i in range(5)]
        got = advertiser_rows(rows, 'yoga', 'US')
        self.assertEqual([(a['pageId'], a['adsFound'], a['landingDomains']) for a in got],
                         [('p1', 3, ['shoeshop.com']), ('p2', 2, ['shoeshop.com'])])
