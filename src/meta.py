"""
Talking to the Meta Ad Library through meta-ads-collector (MIT), over Apify's residential proxy.

Measured on Apify 2026-09-25 ("nike", US, 300 asked): Apify's own IP and the datacenter proxy got
rate-limited to 0 ads; the residential proxy returned 275 unique ads in 185 s with no rate limit,
about $0.037 of platform cost per 1,000 ads. So every search runs on its own residential session
(one IP), and a search that Meta blocks or that errors starts over on a fresh session, at most
twice, skipping ads already delivered.

The library is synchronous (curl_cffi); callers run it in a thread. It takes a single proxy as
host:port:user:pass and splits on ':', so Apify's http://user:pass@host:port is converted here.
"""
import collections
import secrets
from urllib.parse import urlsplit

from meta_ads_collector import (ERROR_OCCURRED, PAGE_FETCHED, RATE_LIMITED, SESSION_REFRESHED, MetaAdsCollector,
                                MetaAdsError)

MAX_ROTATIONS = 2
PAGE_SIZE = 30
RATE_DELAY_S = 1.5      # between the library's requests in one session (its default is 2.0 + 1.0 jitter)
JITTER_S = 1.0


def library_proxy(url: str | None) -> str | None:
    if not url:
        return None
    u = urlsplit(url)
    if u.username:
        return f'{u.hostname}:{u.port}:{u.username}:{u.password}'
    return f'{u.hostname}:{u.port}'


class Session:
    """One residential IP and one library client, with the events it saw."""

    def __init__(self, proxy_url: str | None, factory=MetaAdsCollector):
        self.events: collections.Counter = collections.Counter()

        def on(name):
            return lambda *a, **k: self.events.update([name])
        self.client = factory(proxy=library_proxy(proxy_url), rate_limit_delay=RATE_DELAY_S, jitter=JITTER_S,
                              callbacks={e: on(e) for e in (PAGE_FETCHED, RATE_LIMITED, ERROR_OCCURRED,
                                                            SESSION_REFRESHED)})

    @property
    def blocked(self) -> bool:
        return bool(self.events[RATE_LIMITED] or self.events[ERROR_OCCURRED])


class Sessions:
    """Makes residential sessions. proxy_cfg is an Apify ProxyConfiguration (or None in tests/local)."""

    def __init__(self, proxy_cfg, factory=MetaAdsCollector):
        self.proxy_cfg = proxy_cfg
        self.factory = factory
        self.tag = secrets.token_hex(3)
        self.opened = 0

    async def new(self) -> Session:
        self.opened += 1
        url = await self.proxy_cfg.new_url(f'fb{self.tag}s{self.opened}') if self.proxy_cfg else None
        return Session(url, self.factory)


def search_kwargs(cfg, term: str | None, page_id: str | None, max_results: int | None) -> dict:
    kw = dict(country=cfg.country, ad_type=cfg.ad_type, status=cfg.status, page_size=PAGE_SIZE,
              max_results=max_results, sort_by='SORT_BY_TOTAL_IMPRESSIONS' if cfg.sort == 'impressions' else None)
    if page_id:
        kw.update(search_type='PAGE', page_ids=[page_id], query='')
    else:
        kw.update(search_type='KEYWORD_EXACT_PHRASE' if cfg.exact else 'KEYWORD_UNORDERED', query=term)
    return kw


def resolve_pages(session: Session, name: str, country: str) -> list:
    """Advertiser name -> matching pages (PageSearchResult), best first."""
    return session.client.search_pages(name, country=country if country != 'ALL' else 'US')


__all__ = ['MAX_ROTATIONS', 'MetaAdsError', 'Session', 'Sessions', 'library_proxy', 'resolve_pages', 'search_kwargs']
