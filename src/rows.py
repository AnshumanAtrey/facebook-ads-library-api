"""
Turning Meta's ads into rows people can use.

One ad -> one row with the signals buyers look for: how many days it has run (long runners are the
winners), how many versions it has (Meta's collation count: several live versions = an A/B test),
where it sends people (landing URL and domain), platforms, text, call to action and media links
(Meta's own URLs; nothing is downloaded or re-hosted). Brand scam check and advertiser lists are
built from the same rows.
"""
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .inputs import days_between

LIBRARY_AD = 'https://www.facebook.com/ads/library/?id={}'
PAGE_URL = 'https://www.facebook.com/{}'
PAGE_ADS = 'https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=ALL&view_all_page_id={}'
AD_FIELDS = ('adId', 'adLibraryUrl', 'pageName', 'pageId', 'pageUrl', 'pageLikes', 'pageVerified', 'isActive',
             'startDate', 'endDate', 'daysRunning', 'versions', 'versionGroupId', 'platforms', 'adText', 'headline',
             'description', 'callToAction', 'callToActionType', 'landingUrl', 'landingDomain', 'imageUrls',
             'videoUrls', 'thumbnailUrls', 'cards', 'languages', 'adType', 'categories', 'spend', 'impressions',
             'reach', 'audienceSize', 'ageGender', 'regions', 'targeting', 'fundingEntity', 'disclaimer',
             'beneficiaryPayers', 'searchTerm', 'country', 'impersonation', 'scrapedAt')


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if isinstance(dt, datetime) else str(dt)


def domain_of(url: str | None) -> str | None:
    """The site an ad sends people to, without www. Meta's l.facebook.com redirect is unwrapped."""
    if not url:
        return None
    try:
        parts = urlsplit(url if '://' in url else f'https://{url}')
    except ValueError:
        return None
    host = (parts.hostname or '').lower()
    if host in ('l.facebook.com', 'lm.facebook.com'):
        from urllib.parse import parse_qs
        target = parse_qs(parts.query).get('u', [''])[0]
        return domain_of(target) if target else None
    return host[4:] if host.startswith('www.') else host or None


def _range(r) -> dict | None:
    if r is None or (getattr(r, 'lower_bound', None) is None and getattr(r, 'upper_bound', None) is None):
        return None
    out = {'lower': r.lower_bound, 'upper': r.upper_bound}
    if getattr(r, 'currency', None):
        out['currency'] = r.currency
    return out


def _dist(items) -> list[dict]:
    return [{'group': d.category, 'percent': d.percentage} for d in (items or [])]


def ad_row(ad, search_term: str | None, country: str, now: datetime | None = None) -> dict:
    creatives = list(ad.creatives or [])
    first = creatives[0] if creatives else None
    page = ad.page
    start, stop = _iso(ad.delivery_start_time), _iso(ad.delivery_stop_time)
    landing = next((c.link_url for c in creatives if c.link_url), None)
    images = list(dict.fromkeys(c.image_url for c in creatives if c.image_url))
    videos = list(dict.fromkeys(c.video_hd_url or c.video_url or c.video_sd_url for c in creatives
                                if c.video_hd_url or c.video_url or c.video_sd_url))
    thumbs = list(dict.fromkeys(c.thumbnail_url for c in creatives if c.thumbnail_url))
    cards = [{'headline': c.title, 'text': c.body, 'landingUrl': c.link_url,
              'imageUrl': c.image_url, 'videoUrl': c.video_hd_url or c.video_url or c.video_sd_url}
             for c in creatives] if len(creatives) > 1 else []
    t = ad.targeting
    targeting = None
    if t and (t.age_min or t.age_max or t.genders or t.locations or t.interests):
        targeting = {'ageMin': t.age_min, 'ageMax': t.age_max, 'genders': t.genders, 'locations': t.locations,
                     'excludedLocations': t.excluded_locations, 'interests': t.interests}
    audience = None
    if ad.estimated_audience_size_lower is not None or ad.estimated_audience_size_upper is not None:
        audience = {'lower': ad.estimated_audience_size_lower, 'upper': ad.estimated_audience_size_upper}
    page_id = page.id if page else None
    return {
        'adId': ad.id,
        'adLibraryUrl': LIBRARY_AD.format(ad.id),
        'pageName': page.name if page else None,
        'pageId': page_id,
        'pageUrl': (page.page_url or PAGE_URL.format(page_id)) if page_id else None,
        'pageLikes': page.likes if page else None,
        # Meta's ad search does not say whether a page is verified; the library then reports False for
        # every page (80 of 80 rows on 2026-09-25), so only a True is passed on and unknown stays None.
        'pageVerified': True if page and page.verified else None,
        'isActive': ad.is_active if ad.is_active is not None else (stop is None if start else None),
        'startDate': start,
        'endDate': stop,
        'daysRunning': days_between(start, stop, now),
        'versions': ad.collation_count,
        'versionGroupId': ad.collation_id,
        'platforms': list(ad.publisher_platforms or []),
        'adText': first.body if first else None,
        'headline': first.title if first else None,
        'description': (first.description or first.caption) if first else None,
        'callToAction': first.cta_text if first else None,
        'callToActionType': first.cta_type if first else None,
        'landingUrl': landing,
        'landingDomain': domain_of(landing),
        'imageUrls': images,
        'videoUrls': videos,
        'thumbnailUrls': thumbs,
        'cards': cards,
        'languages': list(ad.languages or []),
        'adType': ad.ad_type,
        'categories': list(ad.categories or []),
        'spend': _range(ad.spend),
        'impressions': _range(ad.impressions),
        'reach': _range(ad.reach),
        'audienceSize': audience,
        'ageGender': _dist(ad.age_gender_distribution),
        'regions': _dist(ad.region_distribution),
        'targeting': targeting,
        'fundingEntity': ad.funding_entity,
        'disclaimer': ad.disclaimer,
        'beneficiaryPayers': list(ad.beneficiary_payers or []),
        'searchTerm': search_term,
        'country': country,
        'impersonation': None,
        'scrapedAt': (now or datetime.now(timezone.utc)).isoformat(timespec='seconds'),
    }


def matches_media(row: dict, media: str) -> bool:
    if media == 'all':
        return True
    if media == 'video':
        return bool(row['videoUrls'])
    if media == 'image':
        return bool(row['imageUrls']) and not row['videoUrls']
    if media == 'none':
        return not row['imageUrls'] and not row['videoUrls']
    return True                                  # meme: Meta's own filter decides; no local signal


# ------------------------------------------------------------ brand scam check --
def _fold(text: str | None) -> str:
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '', text)


def impersonation(row: dict, brand: str, official_ids: set[str], official_domains: set[str]) -> dict | None:
    """Signals that an ad using the brand does not come from the brand. None for the brand's own ads.
    These are signals to review, not a verdict: resellers and affiliates also use brand names."""
    if row['pageId'] and row['pageId'] in official_ids:
        return None
    b = _fold(brand)
    if not b:
        return None
    signals: list[str] = []
    name, domain = _fold(row['pageName']), row['landingDomain'] or ''
    if b in name:
        signals.append('page name uses the brand but it is not an official page')
    if b in _fold(domain) and domain not in official_domains:
        signals.append(f'sends people to {domain}, a look-alike site, not an official domain')
    text = ' '.join(_fold(row[k]) for k in ('adText', 'headline', 'description'))
    if b in text:
        signals.append('ad text names the brand')
    if row['pageLikes'] is not None and row['pageLikes'] < 1000:
        signals.append(f'page has only {row["pageLikes"]} likes')
    if row['daysRunning'] is not None and row['daysRunning'] <= 7:
        signals.append('ad started in the last 7 days')
    strong = any(s.startswith(('page name uses', 'sends people to')) for s in signals)
    weak = sum(s.startswith(('page has only', 'ad started')) for s in signals)
    risk = 'high' if strong and weak else 'medium' if strong or (weak >= 2 and 'ad text names the brand' in signals) \
        else 'low'
    return {'brand': brand, 'risk': risk, 'signals': signals, 'officialPageIds': sorted(official_ids)}


# ------------------------------------------------------------- advertiser list --
def advertiser_rows(ad_rows: list[dict], search_term: str, country: str) -> list[dict]:
    """One row per advertiser behind a keyword: a lead list of pages that are spending on ads now."""
    by: dict[str, dict] = {}
    for r in ad_rows:
        pid = r['pageId']
        if not pid:
            continue
        a = by.setdefault(pid, {'pageName': r['pageName'], 'pageId': pid, 'pageUrl': r['pageUrl'],
                                'pageLikes': r['pageLikes'], 'pageVerified': r['pageVerified'],
                                'adsInLibraryUrl': PAGE_ADS.format(pid), 'adsFound': 0, 'activeAds': 0,
                                'firstAdStarted': None, 'longestRunningDays': 0, 'platforms': set(),
                                'landingDomains': set(), 'sampleAdUrl': r['adLibraryUrl'], 'sampleAdText': r['adText'],
                                'searchTerm': search_term, 'country': country, 'scrapedAt': r['scrapedAt']})
        a['adsFound'] += 1
        a['activeAds'] += bool(r['isActive'])
        if r['startDate'] and (a['firstAdStarted'] is None or r['startDate'] < a['firstAdStarted']):
            a['firstAdStarted'] = r['startDate']
        a['longestRunningDays'] = max(a['longestRunningDays'], r['daysRunning'] or 0)
        a['platforms'].update(r['platforms'])
        if r['landingDomain']:
            a['landingDomains'].add(r['landingDomain'])
    out = []
    for a in sorted(by.values(), key=lambda x: (-x['activeAds'], -x['adsFound'])):
        a['platforms'] = sorted(a['platforms'])
        a['landingDomains'] = sorted(a['landingDomains'])
        out.append(a)
    return out
