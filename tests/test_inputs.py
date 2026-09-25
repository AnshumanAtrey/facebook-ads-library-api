import unittest
from datetime import datetime

from src.inputs import InputError, days_between, page_ref, parse_input


class Keywords(unittest.TestCase):
    def test_only_a_keyword_uses_defaults(self):
        cfg = parse_input({'searchTerms': ['running shoes']})
        self.assertEqual((cfg.mode, cfg.terms, cfg.country, cfg.status, cfg.ad_type, cfg.max_ads),
                         ('ads', ['running shoes'], 'ALL', 'ACTIVE', 'ALL', 100))

    def test_commas_split(self):
        self.assertEqual(parse_input({'searchTerms': ['protein powder, creatine; yoga mat']}).terms,
                         ['protein powder', 'creatine', 'yoga mat'])

    def test_no_keywords_says_what_to_type(self):
        with self.assertRaisesRegex(InputError, 'running shoes'):
            parse_input({})

    def test_sentence_is_refused(self):
        with self.assertRaisesRegex(InputError, 'not a sentence'):
            parse_input({'searchTerms': ['x' * 120]})


class Country(unittest.TestCase):
    def test_names_and_codes(self):
        for typed, code in [('India', 'IN'), ('united states', 'US'), ('USA', 'US'), ('UK', 'GB'), ('de', 'DE'),
                            ('Worldwide', 'ALL'), ('', 'ALL'), ('ALL', 'ALL')]:
            self.assertEqual(parse_input({'searchTerms': ['x'], 'country': typed}).country, code, typed)

    def test_unknown(self):
        with self.assertRaisesRegex(InputError, 'India'):
            parse_input({'searchTerms': ['x'], 'country': 'Atlantis'})


class Links(unittest.TestCase):
    def test_pasted_search_link(self):
        cfg = parse_input({'searchTerms': ['https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=GB'
                                           '&q=protein%20bar&search_type=keyword_unordered&media_type=video']})
        self.assertEqual((cfg.terms, cfg.country, cfg.status, cfg.media_type), (['protein bar'], 'GB', 'ALL', 'video'))

    def test_form_choice_wins_over_link(self):
        cfg = parse_input({'searchTerms': ['https://www.facebook.com/ads/library/?country=GB&q=tea'], 'country': 'India'})
        self.assertEqual(cfg.country, 'IN')

    def test_link_to_one_advertiser_lists_its_ads(self):
        cfg = parse_input({'searchTerms': ['https://www.facebook.com/ads/library/?view_all_page_id=15087023444&country=US']})
        self.assertEqual((cfg.mode, cfg.pages), ('pages', ['15087023444']))

    def test_page_refs(self):
        self.assertEqual(page_ref('https://www.facebook.com/nike'), 'nike')
        self.assertEqual(page_ref('https://www.facebook.com/profile.php?id=100064'), '100064')
        self.assertEqual(page_ref('15087023444'), '15087023444')
        self.assertEqual(page_ref('  Nike   Football '), 'Nike Football')


class Modes(unittest.TestCase):
    def test_pages_mode_uses_keywords_as_names(self):
        cfg = parse_input({'mode': 'pages', 'searchTerms': ['Gymshark']})
        self.assertEqual(cfg.pages, ['Gymshark'])
        self.assertTrue(cfg.notes)

    def test_impersonation_one_brand(self):
        cfg = parse_input({'mode': 'impersonation', 'searchTerms': ['Nike', 'Adidas']})
        self.assertEqual(cfg.terms, ['Nike'])
        self.assertTrue(any('one brand' in n for n in cfg.notes))

    def test_brand_names_keep_their_commas_in_impersonation(self):
        self.assertEqual(parse_input({'mode': 'impersonation', 'searchTerms': ['Crate, Barrel']}).terms, ['Crate, Barrel'])

    def test_filters(self):
        cfg = parse_input({'searchTerms': ['x'], 'status': 'all', 'adType': 'political', 'mediaType': 'video',
                           'minDaysRunning': '30', 'maxAds': 50, 'exactPhrase': True, 'groupVersions': True,
                           'sortBy': 'relevance'})
        self.assertEqual((cfg.status, cfg.ad_type, cfg.media_type, cfg.min_days, cfg.max_ads, cfg.exact,
                          cfg.group_versions, cfg.sort),
                         ('ALL', 'POLITICAL_AND_ISSUE_ADS', 'video', 30, 50, True, True, 'relevance'))

    def test_bad_values(self):
        with self.assertRaisesRegex(InputError, 'Ad status'):
            parse_input({'searchTerms': ['x'], 'status': 'paused'})
        with self.assertRaisesRegex(InputError, 'from 1 to 5000'):
            parse_input({'searchTerms': ['x'], 'maxAds': 0})


class Days(unittest.TestCase):
    def test_days(self):
        now = datetime(2026, 9, 25)
        self.assertEqual(days_between('2026-06-01T12:30:00', None, now), 115)
        self.assertEqual(days_between('2026-09-01T00:00:00', '2026-09-11T00:00:00', now), 10)
        self.assertIsNone(days_between(None, None, now))
