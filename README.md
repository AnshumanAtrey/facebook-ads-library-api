# Meta Ad Library Probe

Private measurement actor. It runs one Ad Library search through `meta-ads-collector` (MIT) from Apify's servers, over no proxy, Apify's datacenter proxy or Apify's residential proxy, and reports how many ads came back, how long it took, and every rate limit, session refresh or error. The run summary is the OUTPUT record; the first 5 ads are saved as dataset rows so the fields can be checked.
