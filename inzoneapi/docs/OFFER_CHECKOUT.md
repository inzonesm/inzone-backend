# Versioned offer checkout

Extends the merged draft catalog in PR #8. This is an opt-in backend API, not a
released iframe SDK or a deployed payment feature. Existing coin-tier routes,
save/load, Firebase providers and Hexclave integration are unchanged.

## What this implements

- Owner publishes the exact draft they inspected into a separate versioned catalog.
- Buyer selects an offer ID and catalog version; the server reads price/kind/quantity.
- One Firestore transaction debits `humanUsers.balance`, writes the existing
  `game_coin_transactions` receipt and `game_revenue_summary` accounting fields,
  grants inventory, records request binding and increments the purchase limit.
- Same player/game/request ID returns the original receipt. Changing its offer or
  catalog version returns 409. Keep IDs stable when retrying uncertain requests.
- Concurrent durable purchases return the first receipt without charging again.
- Consumables add the stored quantity. This PR grants balances; consuming units,
  refunds, revocation, subscriptions and cash settlement are separate operations.
- Inventory lookup and request receipt recovery are available even after game or
  catalog removal. Receipt `newBalance` is historical, not the current wallet balance.

No route accepts a client price, quantity or userId. Firebase UID comes from the
verified, revocation-checked bearer token. This token belongs in the trusted host,
not an uploaded game or public game configuration. The player-facing confirmation
screen and safe host-to-game communication remain the next frontend integration.

## Activation and known shared-wallet dependency

Both `INZONE_OFFER_CHECKOUT_ENABLED=1` and
`INZONE_OFFER_CHECKOUT_WALLET_READY=1` are required; otherwise every new route is
404. Leave both unset in production. Catalog authoring keeps its separate flag.

**The second flag is a rollout attestation, not a concurrency mechanism.**
The in-repository wallet writers now use transactions or atomic credit increments;
see [Shared wallet transactions](SHARED_WALLET_TRANSACTIONS.md) for coverage and
compatibility changes. Mixed legacy/new emulator tests cover competing debits,
credits and accounting. This is source-level evidence, not proof that every live
writer has been upgraded. Before activation, deploy the cooperating writers
(including the separate agent service), inventory external/client writers and
verify their isolation. Do not enable by merely setting the flag.

Also verify deployed Firestore rules deny client writes to `game_offer_catalogs`,
`game_offer_requests`, `game_product_inventory`, `game_checkout_limits` and the
wallet/accounting documents. Review read rules for player receipt/inventory
privacy. The backend repository does not own deployed rules. A trusted host
confirmation and isolation boundary are required before giving games access.
No live Firebase auth, live rules, WSGI deployment or real coin balances were used.

## Endpoints

All paths start `/api/game-sdk/v2/games/{gameId}`. Responses are non-cacheable.
Identifiers use 1–100 alphanumeric/underscore/hyphen characters. Authentication:
`Authorization: Bearer <Firebase ID token>`; do not place tokens in URLs.

| Method/path | Caller | Request / result |
|---|---|---|
| POST `/catalog/publish` | Verified `uploaderId` owner | `{"offers":[...]}` exactly matching the inspected draft; returns version and offers |
| GET `/catalog` | Public | Published version/offers for approved game; no owner UID exposed |
| POST `/purchases` | Verified player | `{offerId, catalogVersion, requestId}`; returns receipt and fulfillment snapshot |
| GET `/purchases/{requestId}` | Same verified player | Original receipt, including durable restore aliases |
| GET `/inventory/{offerId}` | Verified player | Owned flag, quantity, kind and last purchase ID, scoped to this game/player |

Publishing normalizes the same validated offer schema as PR #8. Changed drafts
return `DRAFT_CHANGED`; old checkout versions return `OFFER_CHANGED`. Refresh
catalog and obtain renewed user confirmation before generating a new request.
New publishes do not change prior receipts. Product IDs represent stable products;
changing durable/consumable kind, even after removal, is rejected.

Example purchase after presenting the published title, price and quantity:

```json
{"offerId":"extra-lives","catalogVersion":"<published-version>","requestId":"<persisted-unique-id>"}
```

The response's `coins` and `entitlement.quantity` describe the confirmed purchase
and its inventory snapshot. A replay returns that historical snapshot verbatim;
query inventory for the latest quantity. Never grant extra consumables merely
because the same receipt arrived twice. Retain request bindings and receipts;
deleting them invalidates retry guarantees.

New successful purchases are limited to 30 per player/game/minute transactionally.
Retries and existing durable restores do not consume another purchase slot. This
is not an edge request-rate limiter; deploy gateway limits for unauthenticated or
rejected traffic separately. Commission uses the existing service's configured
`COIN_COMMISSION_RATE` and rounding; no new payout/economic policy is introduced.
Offer counts use `offer_breakdown`, preserving existing `tier_breakdown` semantics.
Game activity/retention counters are not incremented by this checkout yet.

## Tests and reproduction

Install test-only dependencies in a virtual environment (no service credentials):

```sh
python -m pip install Flask google-cloud-firestore
python inzoneapi/scripts/test_offer_checkout_emulator.py /path/to/cloud-firestore-emulator.jar
PYTHONPATH=inzoneapi python -m unittest discover -s inzoneapi/tests -p test_game_offers.py -v
```

The runner launches a loopback emulator under `demo-inzone-checkout`, uses anonymous
credentials and shuts it down afterward. It needs Java and an installed Firestore
emulator JAR. Executed here with Python 3.12, Java 17 and Firestore emulator 1.19.8.
Fourteen emulator tests and six existing catalog tests passed. Checks include
simultaneous identical requests, competing requests against insufficient funds,
simultaneous durable purchases, rollback after buffered writes, stale prices,
owner transfer, malformed/auth-spoofing requests, request conflicts and restoration.
Firebase token verification is injected in HTTP tests; Firestore transactions are
real emulator transactions, not an in-memory transaction imitation.

## Review and subsequent work

Review this PR against `game-analytics`; do not retarget to `main`. Keep activation
off. The shared-wallet implementation and mixed tests are documented separately.
Next connect the trusted web checkout confirmation and packaged SDK call to these
endpoints, verify rules/identity integration, and validate a test deployment.
