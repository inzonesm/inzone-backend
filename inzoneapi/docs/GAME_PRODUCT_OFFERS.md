# Developer-defined offers: first monetization increment

Base: `game-analytics` at `ef1ccef541abd7c408084a351f1de01ad0928d8b`.
This branch contains the existing game SDK backend. `main` does not contain
these routes. Deployment provenance is not verified by this source inspection.

## Existing behavior retained

`routes/api/social_loop.py` exposes the four coin-tier routes, game-state and
save/load. `SocialLoopService.purchase_coin_tier` delegates to
`_build_coin_response`: humanUsers balance, game_coin_transactions receipts,
game_revenue_summary and activity records. These files and methods are unchanged.

The new increment lets web upload owners author a catalog of durable access and
consumables, with integer coin prices independent of the four fixed tiers.
It adds a real persistence API, not a checkout simulation. All offers remain
**draft**, and every successful response explicitly says `purchaseSupported: false`.
No game should display these as purchasable yet. No Studio UI or player SDK
purchase method is added by this PR.

## API (off by default)

Set `INZONE_OFFER_CATALOG_ENABLED=1` only in a reviewed test deployment first.
`GET` and `PUT /api/game-sdk/games/{gameId}/offers` require the web owner's
Firebase ID token in `Authorization: Bearer ...`. Server verification checks
revocation. Owner identity is matched against `html_games/{gameId}.uploaderId`.
Legacy developer_id records without this verified mapping are rejected; do not
invent an owner mapping or pass a game key instead of a Firebase token.

PUT replaces the complete draft catalog (maximum 100 offers / 64 KiB request).
Draft editing is last-write-wins. Empty array clears the catalog.

```json
{"offers":[
  {"id":"full-game","title":"Full game","kind":"durable","coins":37,"quantity":1},
  {"id":"extra-lives","title":"Five lives","kind":"consumable","coins":23,"quantity":5}
]}
```

IDs must be unique alphanumeric/underscore/hyphen strings. Titles: 1–120
characters. Prices: integer 1–1000000; quantities: integer 1–10000, exactly 1
for durable access. Booleans, extra fields and unsupported kinds are rejected.
These are draft schema bounds, not economic recommendations or payout promises.
Subscription/fiat/usage billing requires separate settlement contracts and is not
silently approximated using consumables.

Storage: one `game_offer_drafts/{gameId}` document. No wallet, save, inventory,
revenue or existing game document writes. Before enabling, verify deployed
Firestore rules deny direct client writes to this collection. This PR neither
changes rules nor claims to have tested the live rules.

## Verification

```sh
PYTHONPATH=inzoneapi python -m unittest discover -s inzoneapi/tests -p test_game_offers.py -v
```

Six tests passed using Flask's real HTTP test client with injected in-memory
storage and token verification. Tests cover custom prices/kinds, persistence,
owner access, invalid token, legacy identity rejection, invalid payloads,
disabled state, clearing and missing games. Firebase verification and Firestore
execution were not tested against a live service/emulator. No charges performed.
Python compilation and whitespace validation also passed.

## Next implementation: purchase by stored offer ID

Do not route custom offers to the nearest existing tier. Do not send an arbitrary
client price into the tier API. Preserve old tier calls while adding an explicitly
versioned offer checkout.

Before that new checkout can charge, its transaction must bind verified player,
game, offer and request ID, load the stored offer price/version, and atomically
write the debit, receipt, fulfillment and existing revenue accounting fields.
Durables must restore without recharging; consumables need atomic quantity
updates. Retried request IDs must return the original receipt, not debit again.

Reason grounded in inspected code: `_build_coin_response` currently updates the
balance then writes transaction and summary documents separately, and accepts a
transaction ID without reading a prior receipt. This is not a claim that existing
users' purchases failed; it means we cannot reuse it blindly for new fulfillment
and retry guarantees. Save/load is unrelated and remains untouched.

Review catalog ownership/validation first. Next PR can extend the actual payment
service now that its source and accounting collections have been located.
