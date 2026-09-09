# 09 Provider licensing and cost checklist

To be completed and signed off before any non-demo environment. Nothing below has been confirmed in this build.

- [ ] Market data vendor selected; contract permits internal use, storage of history, derived indicators and display to the end user.
- [ ] Redistribution clauses reviewed (no redistribution to third parties is planned).
- [ ] Bid/ask availability confirmed (required for honest cost modelling); if mid-only, the DEGRADED integrity flag remains visible to users.
- [ ] Economic calendar vendor selected; consensus/revision fields and publication timestamps contractually available.
- [ ] Dollar index: confirm ICE DXY licence or switch to the public FX-basket proxy (already the default expectation in the regime engine, which only needs a "dollar strength proxy").
- [ ] CFTC, FRED, Treasury: attribution text prepared.
- [ ] ETF flow source: WGC/issuer terms of use reviewed.
- [ ] Trading calendar source: CME/LBMA notices process documented.
- [ ] Push service: browser push services are free; if FCM is used, Firebase terms reviewed; no analytics SDKs.
- [ ] Cost estimate: market data (paid tier), calendar (paid), everything else free; document monthly budget and rate-limit headroom for a 60-second analysis interval (about 1,440 quote calls and 7,000 candle rows per day per provider).
- [ ] Key rotation and storage in the platform secret manager.
