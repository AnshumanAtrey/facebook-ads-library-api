# Changelog

## 2026-10-30

- Apify SDK 4 (`apify>=4.1,<5`): SDK 3.4.1 raised on runs started by Apify's AI assistant (run origin
  APIFY_AI) wherever a status message was read back. 44 tests pass (a date-dependent test now counts days from today); the example gave 20 ads and 20 charges locally.
- Store discounts: 10% off on Scale, 20% off on Business and above; Free and Starter prices unchanged.
- Three example tasks on the Store (`.actor/tasks.json`, published by CI).

## 1.0 (2026-09-25)
- Four report types: ads for keywords, ads of advertisers, advertiser list, brand scam check.
- daysRunning, versions, landing domain and every creative link on each ad; filters for status, ad category, media type, minimum days live, exact phrase and merged versions.
- Every search on Apify's residential proxy (Meta blocks cloud and datacenter IPs); a blocked search restarts on a fresh IP, at most twice.
- Pay per ad and per advertiser, charged per saved batch; a spending limit stops the run cleanly.
