"""
Input: what people type, turned into searches.

Built for two people at once (manager/rules/SEO.md section 11.5): someone who only types a keyword
gets a full, useful result, and a technical user can set every field. So keywords split on commas,
a pasted Ad Library link gives its search, country, status and ad type, a Facebook page link or name
is an advertiser, country names work as well as codes, and every change we make is a plain note.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MODES = ('ads', 'pages', 'advertisers', 'impersonation')
STATUSES = {'active': 'ACTIVE', 'inactive': 'INACTIVE', 'all': 'ALL'}
AD_TYPES = {'all': 'ALL', 'political': 'POLITICAL_AND_ISSUE_ADS', 'housing': 'HOUSING_ADS',
            'employment': 'EMPLOYMENT_ADS', 'credit': 'CREDIT_ADS'}
MEDIA_TYPES = ('all', 'image', 'video', 'meme', 'none')
SORTS = ('impressions', 'relevance')
MAX_TERM_CHARS = 100
MAX_ADS_CAP = 5000
COUNTRIES: dict[str, str] = json.loads((Path(__file__).parent / 'countries.json').read_text(encoding='utf-8'))
WORLDWIDE = {'', 'ALL', 'WW', 'WORLDWIDE', 'GLOBAL', 'WORLD', 'ANY'}
NAME_ALIASES = {'USA': 'US', 'U.S.': 'US', 'U.S.A.': 'US', 'AMERICA': 'US', 'UNITED STATES OF AMERICA': 'US',
                'UK': 'GB', 'ENGLAND': 'GB', 'BRITAIN': 'GB', 'GREAT BRITAIN': 'GB', 'SOUTH KOREA': 'KR',
                'KOREA': 'KR', 'UAE': 'AE', 'RUSSIA': 'RU', 'VIETNAM': 'VN', 'TURKEY': 'TR', 'HOLLAND': 'NL',
                'CZECH REPUBLIC': 'CZ'}
AD_LIBRARY = re.compile(r'^https?://([a-z]+\.)?facebook\.com/ads/library', re.I)
FACEBOOK = re.compile(r'^https?://([a-z-]+\.)?(facebook|fb)\.(com|me)/', re.I)
SPLIT = re.compile(r'[,;]')


class InputError(ValueError):
    """Input we cannot run; the message says what to type instead."""


@dataclass
class Config:
    mode: str = 'ads'
    terms: list[str] = field(default_factory=list)          # keywords (ads, advertisers) or the brand (impersonation)
    pages: list[str] = field(default_factory=list)          # page ids, page links or advertiser names (pages)
    official: list[str] = field(default_factory=list)       # the brand's own pages (impersonation)
    country: str = 'ALL'
    status: str = 'ACTIVE'
    ad_type: str = 'ALL'
    media_type: str = 'all'
    min_days: int = 0
    max_ads: int = 100
    exact: bool = False
    group_versions: bool = False
    sort: str = 'impressions'
    notes: list[str] = field(default_factory=list)          # plain-English changes we made to the input


def _upper_plain(text: str) -> str:
    up = ' '.join(str(text).split()).upper()
    return unicodedata.normalize('NFKD', up.replace('’', "'")).encode('ascii', 'ignore').decode()


COUNTRY_BY_NAME = {**{_upper_plain(v): k for k, v in COUNTRIES.items()},
                   **{_upper_plain(v).replace(' & ', ' AND '): k for k, v in COUNTRIES.items()}, **NAME_ALIASES}


def parse_country(value) -> str:
    text = _upper_plain(value or '')
    if text in WORLDWIDE:
        return 'ALL'
    text = COUNTRY_BY_NAME.get(text, text)
    if text not in COUNTRIES:
        raise InputError(f'Country (country) "{value}" is not a country we know. Pick it from the list, type a name '
                         f'such as India or a two-letter code such as IN, or leave it on Worldwide (ALL).')
    return text


def _choice(value, allowed, default, label: str, key: str):
    if value is None or str(value).strip() == '':
        return default
    v = str(value).strip().lower().replace('_', '-')
    if v not in allowed:
        raise InputError(f'{label} ({key}) must be one of {", ".join(allowed)}, not "{value}".')
    return v


def _int(value, default: int, lo: int, hi: int, label: str, key: str) -> int:
    if value is None or str(value).strip() == '':
        return default
    try:
        n = int(float(str(value).strip()))
    except ValueError:
        raise InputError(f'{label} ({key}) must be a whole number, not "{value}".') from None
    if not lo <= n <= hi:
        raise InputError(f'{label} ({key}) must be from {lo} to {hi}, not {n}.')
    return n


def _items(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return value.splitlines()
    if isinstance(value, list):
        return value
    raise InputError('Lists such as Keywords (searchTerms) take one entry per line.')


def read_library_link(url: str) -> dict:
    """What a pasted Ad Library link asks for: q, country, active_status, ad_type, media_type, view_all_page_id."""
    q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items() if v}
    return {'q': q.get('q', '').strip(), 'country': q.get('country'), 'status': q.get('active_status'),
            'ad_type': q.get('ad_type'), 'media_type': q.get('media_type'), 'page': q.get('view_all_page_id'),
            'exact': q.get('search_type') == 'keyword_exact_phrase'}


def page_ref(text: str) -> str:
    """A page id, a Facebook page link, or a name to look up. Returns the id or the cleaned text."""
    text = text.strip()
    if text.isdigit():
        return text
    if FACEBOOK.match(text):
        parts = urlsplit(text)
        q = parse_qs(parts.query)
        if q.get('id', [''])[0].isdigit():
            return q['id'][0]
        path = [p for p in parts.path.split('/') if p]
        if path[:1] == ['people'] and len(path) >= 3 and path[2].isdigit():
            return path[2]
        if path and path[0] not in ('pages', 'profile.php', 'groups', 'watch', 'events'):
            return path[0]                        # a vanity name: resolved by name later
        if len(path) >= 3 and path[0] == 'pages' and path[2].isdigit():
            return path[2]
    return ' '.join(text.split())


def parse_input(raw: dict | None) -> Config:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise InputError('The input must be a JSON object, as the input form produces.')
    mode = _choice(raw.get('mode'), MODES, 'ads', 'Report type', 'mode')
    cfg = Config(mode=mode)
    link: dict = {}
    terms: list[str] = []
    pages: list[str] = []
    for item in _items(raw.get('searchTerms')):
        text = str(item or '').strip()
        if not text:
            continue
        if AD_LIBRARY.match(text):
            got = read_library_link(text)
            link = link or got
            if got['page']:
                pages.append(got['page'])
            elif got['q']:
                terms.append(got['q'])
            cfg.notes.append('Read the search from the Ad Library link.')
            continue
        terms += [t.strip() for t in SPLIT.split(text) if t.strip()] if mode != 'impersonation' else [text]
    for item in _items(raw.get('pages')):
        text = str(item or '').strip()
        if not text:
            continue
        if AD_LIBRARY.match(text):
            got = read_library_link(text)
            link = link or got
            if got['page']:
                pages.append(got['page'])
            continue
        pages += [page_ref(t) for t in (SPLIT.split(text) if not FACEBOOK.match(text) else [text]) if t.strip()]
    official = [page_ref(str(t)) for t in _items(raw.get('officialPages')) if str(t or '').strip()]

    too_long = [t for t in terms if len(t) > MAX_TERM_CHARS]
    if too_long:
        raise InputError(f'"{too_long[0][:60]}..." is longer than {MAX_TERM_CHARS} characters. Enter a keyword or '
                         f'brand name, not a sentence.')
    cfg.terms = list(dict.fromkeys(terms))
    cfg.pages = list(dict.fromkeys(pages))
    cfg.official = list(dict.fromkeys(official))

    if mode == 'ads' and cfg.pages and not cfg.terms:
        mode = cfg.mode = 'pages'
        cfg.notes.append('Only advertisers were given, so the run lists their ads.')
    if mode in ('ads', 'advertisers') and not cfg.terms:
        raise InputError('No keywords to search. Enter at least one in Keywords (searchTerms), for example running '
                         'shoes, or paste an Ad Library search link.')
    if mode == 'pages' and not cfg.pages:
        if cfg.terms:
            cfg.pages, cfg.terms = cfg.terms, []
            cfg.notes.append('The keywords were used as advertiser names.')
        else:
            raise InputError('No advertisers given. Enter a Facebook page link, page id or advertiser name in '
                             'Advertisers (pages), for example https://www.facebook.com/nike.')
    if mode == 'impersonation':
        if not cfg.terms:
            raise InputError('Enter the brand to protect in Keywords (searchTerms), for example Nike.')
        if len(cfg.terms) > 1:
            cfg.notes.append(f'The brand scam check takes one brand per run; checking "{cfg.terms[0]}".')
            cfg.terms = cfg.terms[:1]

    def from_link(key: str, value, default):
        if link.get(key) and (value is None or str(value).strip().upper() in ('', str(default).upper())):
            cfg.notes.append(f'Used {key} "{link[key]}" from the Ad Library link.')
            return link[key]
        return value

    cfg.country = parse_country(from_link('country', raw.get('country'), 'ALL'))
    status = from_link('status', raw.get('status'), 'active')
    cfg.status = STATUSES[_choice(status, tuple(STATUSES), 'active', 'Ad status', 'status')]
    ad_type = from_link('ad_type', raw.get('adType'), 'all')
    ad_type = {'political_and_issue_ads': 'political'}.get(str(ad_type or '').lower(), ad_type)
    cfg.ad_type = AD_TYPES[_choice(ad_type, tuple(AD_TYPES), 'all', 'Ad category', 'adType')]
    cfg.media_type = _choice(from_link('media_type', raw.get('mediaType'), 'all'), MEDIA_TYPES, 'all',
                             'Media type', 'mediaType')
    cfg.min_days = _int(raw.get('minDaysRunning'), 0, 0, 3650, 'Min days live', 'minDaysRunning')
    cfg.max_ads = _int(raw.get('maxAds'), 100, 1, MAX_ADS_CAP, 'Ads per search', 'maxAds')
    cfg.exact = bool(raw.get('exactPhrase')) or bool(link.get('exact'))
    cfg.group_versions = bool(raw.get('groupVersions'))
    cfg.sort = _choice(raw.get('sortBy'), SORTS, 'impressions', 'Order', 'sortBy')
    return cfg


def days_between(start: str | None, stop: str | None, now: datetime | None = None) -> int | None:
    """Whole days an ad has run: to its stop date, or to now when it is still running."""
    if not start:
        return None
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(stop) if stop else (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    except ValueError:
        return None
    a, b = a.replace(tzinfo=None), b.replace(tzinfo=None)
    return max(0, (b - a).days)
