# Facebook Ads Library Scraper API - Winning Ads & Scam Check

Scrape the Meta Ad Library (Facebook, Instagram, Messenger, Threads and Audience Network ads) with no login, no cookies and no Meta API token. Type a keyword or paste a Facebook page, and get every matching ad as a row: the advertiser, **how many days the ad has run**, **how many versions it has**, the text, headline and button, **the landing page and its domain**, image and video links, platforms, and the reach, spend and EU audience data Meta publishes. On top of that: an **advertiser list** (businesses advertising on a keyword right now, one row each) and a **brand scam check** (ads that use a brand's name from pages that are not the brand's own). **$0.70 per 1,000 ads**, no start fee. Use it from the Apify Console, the API, Python, JavaScript, n8n, Make, Zapier or an AI agent through the Apify MCP server.

## What does it do?

It reads the public Meta Ad Library, the same one at facebook.com/ads/library, and returns what you would otherwise copy by hand, for as many keywords or advertisers as you give it:

- **Ads for keywords (`ads`)**: every ad matching your words in a country or worldwide.
- **Ads of advertisers (`pages`)**: all ads of the Facebook pages you list, by link, page id or just the name.
- **Advertiser list (`advertisers`)**: the businesses advertising on your keywords now, with how many ads, their longest-running ad and the websites they send people to.
- **Brand scam check (`impersonation`)**: ads that name a brand but come from other pages, each with a risk level and the signals behind it (look-alike page name, look-alike landing domain, a new ad from a small page).

## Why do people use the Ad Library data?

**Answer: to see what already works in someone else's ads.** Meta shows every running ad but no results, so the best free signal is time: an ad that has run for 30 to 90 days is almost always paying for itself, because nobody keeps paying for an ad that loses money.

- **Media buyers and DTC brands** find competitors' long-running ads and copy the hook, offer and format instead of paying to test from zero. `daysRunning` and `versions` are here for that: several live versions of one ad are an A/B test, and the survivors are the winners.
- **Creative strategists and agencies** keep a weekly watchlist of 10 to 20 brands and build swipe files; the landing domain shows the funnel behind each ad.
- **Agencies prospecting** use the advertiser list: a business spending on ads now has a budget, so it is a warm lead.
- **E-commerce and dropshipping** spot products pushed with many long-running ads.
- **Developers** build ad-spy tools, n8n and Make flows (scrape, then have GPT or Gemini pull out hooks and write new variations) and AI-agent tools on top of it, without maintaining a scraper.
- **Brand protection and security teams** run the brand scam check. Meta itself estimated about 15 billion scam ads are shown every day and expanded its brand-impersonation detection in March 2026; this finds the ones using your name.

## How is it different from other Facebook Ads Library scrapers?

- **Winning-ad signals built in**: `daysRunning` is computed for every ad, `versions` is Meta's own count of an ad's variants, and **Min days live (`minDaysRunning`)** keeps only the long runners.
- **Landing domain on every ad**, so you can group ads by the site they send people to.
- **Advertiser list and brand scam check** in the same actor, charged the same way.
- **Simple for anyone**: type a keyword and press Start; country names work (India, USA, UK), commas split keywords, and a pasted Ad Library link or Facebook page link is understood.
- **No proxy to set up**: Meta blocks cloud and datacenter IPs (in our 2026-09-25 test both returned 0 ads), so every search runs on Apify's residential proxy, included in the price.
- **You pay only for rows saved**, and a spending limit stops the run cleanly between batches.

## How much does it cost to scrape the Facebook Ads Library?

**$0.0007 per ad ($0.70 per 1,000)**, **$0.008 per advertiser** in the Advertiser list and **$0.002 per ad** in the brand scam check (it first reads the brand's own pages to learn their real websites). No start fee, no monthly fee, platform usage and residential proxy included.

| Run | Charged | Price |
|---|---|---|
| The example input (20 ads for "running shoes") | 20 ads | $0.014 |
| 100 ads for one keyword | 100 ads | $0.07 |
| 1,000 ads across 10 keywords | 1,000 ads | $0.70 |
| Advertiser list from 200 ads, 60 advertisers found | 60 advertisers | $0.48 |
| Brand scam check that finds 40 ads from other pages | 40 scam-check ads | $0.08 |
| A search where Meta has no matching ads | 0 | $0.00 |

Apify's free plan includes $5 of monthly credit, which covers about 7,000 ads.

## How does the price compare with other Facebook Ads Library scrapers?

The Facebook Ads Library actors with 250 or more users in the last 30 days on 2026-09-25, ordered by those users, at their Apify free-plan price.

| Scraper | Price per 1,000 ads | Start fee | Users, 30 days |
|---|---|---|---|
| **This actor** | **$0.70** | **None** | **New** |
| [Facebook Ads Library Scraper](https://apify.com/apify/facebook-ads-scraper) by apify | $5.80 | None | 6,040 |
| [Facebook Ads Library Scraper](https://apify.com/curious_coder/facebook-ads-library-scraper) by curious_coder | $0.75 | $0.00005 | 5,853 |
| [Facebook Ad Library Scraper](https://apify.com/igolaizola/facebook-ad-library-scraper) by igolaizola | $0.75 | $0.0075 | 1,048 |
| [Facebook Ads Library](https://apify.com/automation-lab/facebook-ads-library) by automation-lab | $0.575 | $0.005 | 458 |
| [Facebook Ads Library Scraper](https://apify.com/memo23/facebook-ads-library-scraper-ppe) by memo23 | $0.50 | $0.05 | 340 |
| [Facebook Ads Library Scraper](https://apify.com/brilliant_gum/facebook-ads-library-scraper) by brilliant_gum | $15.00 + platform usage | $0.001 | 271 |
| [Meta Ad Scraper](https://apify.com/whoareyouanas/meta-ad-scraper) by whoareyouanas | $10.00 | None | 256 |
| [Meta Ad Library Scraper](https://apify.com/jmlp/meta-ad-library-scraper) by jmlp | $0.15 + platform usage | None | 254 |

Several of these discount their prices on paid Apify plans, and some bill platform usage on top; automation-lab, memo23 and jmlp cost less per ad on large runs. Compare at your own plan if you run large volumes.

## Which inputs does it take?

Every field has a plain name with its JSON key in brackets. Only Keywords is needed.

| Field (JSON key) | Required | What it does |
|---|---|---|
| Report type (`mode`) | No | `ads` (default), `pages`, `advertisers` or `impersonation` (brand scam check) |
| Keywords (`searchTerms`) | Yes, except for `pages` | One per line; `a, b` on one line is two keywords; a pasted Ad Library search link works. For the scam check, the brand |
| Advertisers (`pages`) | For `pages` | Facebook page links, page ids or names, for example `https://www.facebook.com/nike` or `Gymshark` |
| Country (`country`) | No | `ALL` (worldwide, default), a name such as `India` or a code such as `IN` |
| Ads per search (`maxAds`) | No | Most ads saved per keyword or advertiser, default 100 |
| Ad status (`status`) | No | `active` (default), `inactive` or `all` |
| Ad category (`adType`) | No | `all` (default), `political`, `housing`, `employment`, `credit` |
| Media type (`mediaType`) | No | `all`, `image`, `video`, `meme`, `none` |
| Min days live (`minDaysRunning`) | No | Keep only ads that ran at least this many days |
| Exact phrase (`exactPhrase`) | No | Match the keywords as one phrase |
| Merge versions (`groupVersions`) | No | One row per group of ad versions |
| Order (`sortBy`) | No | `impressions` (most seen first, default) or `relevance` |
| Official pages (`officialPages`) | No | For the scam check: the brand's own pages; left empty, pages named exactly like the brand are used and listed in the run summary |

```json
{ "searchTerms": ["running shoes"], "country": "US", "minDaysRunning": 30, "maxAds": 200 }
```

## What does the output look like?

One row per ad (or per advertiser in the Advertiser list). Every key is always present, empty when Meta has no such part. An example ad row, shortened:

```json
{
  "adId": "866569929827744",
  "adLibraryUrl": "https://www.facebook.com/ads/library/?id=866569929827744",
  "pageName": "Example Brand",
  "pageId": "1234567890",
  "pageLikes": 48210,
  "isActive": true,
  "startDate": "2026-06-01T12:30:00",
  "daysRunning": 116,
  "versions": 3,
  "platforms": ["FACEBOOK", "INSTAGRAM", "THREADS"],
  "adText": "Our best-selling trainer is back in stock...",
  "headline": "Free shipping this week",
  "callToAction": "Shop now",
  "landingUrl": "https://www.example.com/sale",
  "landingDomain": "example.com",
  "imageUrls": ["https://scontent.xx.fbcdn.net/..."],
  "videoUrls": [],
  "spend": null,
  "ageGender": [],
  "impersonation": null
}
```

Brand scam check rows add `impersonation`: `{"brand": "Nike", "risk": "high", "signals": ["page name uses the brand but it is not an official page", "sends people to nike-outlet-sale.shop, a look-alike site, not an official domain"]}`. The signals are for you to review, not a verdict: resellers such as Foot Locker also use brand names and come back as low risk.

The run summary is the OUTPUT record: status, notes about anything we changed in your input, one entry per search with how many ads were read and saved, and the charged events.

## How fast is it?

In our 2026-09-25 tests on Apify (256 MB, peak 57-70 MB): 20 ads in 16 s, 200 ads for one keyword in 106 s, 3 keywords of 50 ads each in 49 s (they run at once, each on its own residential IP), 60 ads of 2 advertisers in 48 s, and an advertiser list of 86 businesses from 100 ads in 66 s. No run was rate-limited.

## Common questions

**Q: Do I need a Facebook account, cookies or a Meta API token?**
No. It reads the public Ad Library the way a logged-out visitor sees it.

**Q: Can I see how much an ad spends or how many people it reached?**
For political and issue ads, yes: Meta publishes spend and impressions ranges. For ads delivered in the EU, Meta publishes reach by age, gender and region. For other ads Meta shows no numbers, which is why `daysRunning` and `versions` matter.

**Q: How do I find winning ads?**
Set Min days live (`minDaysRunning`) to 30 or more. Ads that keep running for weeks are the ones making money, and `versions` shows which ones are being tested in several variants.

**Q: Is this the official Meta Ad Library API?**
No. The official API needs a developer account and identity verification and covers political and issue ads plus ads shown in the EU. This actor covers every ad the public Ad Library shows.

**Q: Can I monitor competitors every week?**
Yes. Save the input as an Apify task and schedule it; Ad status (`status`) `active` with Order (`sortBy`) `impressions` gives the ads that matter first.

**Q: Why do I need a residential proxy?**
You do not set one up. Meta rate-limits cloud and datacenter IPs to zero ads, so the actor uses Apify's residential proxy for you and the price includes it.

**Q: Does it download images and videos?**
No. It returns Meta's own image and video links; download them yourself if you need copies.

**Q: What does the brand scam check look for?**
Pages whose name uses the brand but are not the official pages, ads that send people to a look-alike domain, and new ads from small pages. It skips the brand's own pages, found by name or given by you.

## Limitations

- Meta shows spend and impressions only for political and issue ads, and audience breakdowns only for ads delivered in the EU.
- Whether a page is verified is not in Meta's ad search results, so the actor does not guess it.
- Keyword search follows Meta's own matching, which can return loosely related ads; turn on Exact phrase (`exactPhrase`) for tighter matches.
- Very large searches take time: about 110 ads a minute per keyword (200 in 106 s on Apify); several keywords run at once.

## About the maintainer (priority response within 1-2 hours)

Built and maintained by **Anshuman Atrey** ([@AnshumanAtrey](https://github.com/AnshumanAtrey)).

- Purple-team security researcher, 5x hackathon winner
- Co-founder of **Walrus Securitas** (AI cybersecurity SaaS) and **The Drone Syndicate** (autonomous defence drones)
- Author of the OSINT and data actor portfolio on Apify Store: 18 shipped actors covering email, phone, username, IP and domain, network, secret, social, LinkedIn, domain history, Telegram, Google Trends, Meta ads and Indian fintech data

### Custom feature requests shipped within 1-2 hours (priority)

If you need a field, a filter or an output format this actor does not have, the maintainer ships it directly into this actor, typically within 1-2 hours for priority requests during active hours and within 24 hours overnight. This is direct one-to-one service from the maintainer, not a contractor queue.

**Fastest contact channels (ranked by response speed):**
1. **LinkedIn DM** -> [linkedin.com/in/anshumanatrey](https://linkedin.com/in/anshumanatrey), typically under 1 hour during active hours
2. **GitHub issue** on this actor's repo
3. **Apify Console** DM to `@anshumanatrey`
4. **Email** via [atrey.dev](https://atrey.dev)

---

## Sibling actors by the same maintainer

| Actor | Use case |
|---|---|
| [google-trends-api-scraper](https://apify.com/anshumanatrey/google-trends-api-scraper) | Google Trends interest over time, regions, related queries and Trending Now, no login |
| [domain-history-contact-osint](https://apify.com/anshumanatrey/domain-history-contact-osint) | A domain's previous owners, emails and history: pair it with the landing domains found here |
| [netintel](https://apify.com/anshumanatrey/netintel) | IP or domain intelligence: WHOIS, DNS, GeoIP, ASN, ports, for look-alike scam domains |
| [telegram-channel-scraper](https://apify.com/anshumanatrey/telegram-channel-scraper) | Posts, media and buttons from public Telegram channels, no login |
| [theharvester-osint](https://apify.com/anshumanatrey/theharvester-osint) | Emails, subdomains and hosts of a domain from public sources |
| [holehe-email-osint](https://apify.com/anshumanatrey/holehe-email-osint) | Which of 120+ sites an email is registered on |

## Documentation

- Apify API: https://docs.apify.com/api/v2
- Run it from Python or JavaScript with the Apify client, or from n8n, Make and Zapier through their Apify integrations.
- Source: https://github.com/AnshumanAtrey/facebook-ads-library-api

## Last updated

2026-09-25: version 1.0.
