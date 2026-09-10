# Shared wallet transactions

Base: `game-analytics` at `2878e7b3107d5bdf394d64d992105959b71aa850` (merged PR #9).

Legacy balance read/modify/write operations could erase a concurrent offer debit
or spend the same funds twice. This change makes the existing writers cooperate
with offer checkout. It does not replace save/load or change offer pricing.

## Changes and compatibility

- Legacy coin tiers: wallet debit, receipt creation and revenue summary increments
  commit together. Existing success fields and tier/SDK/payment envelope remain.
  Supplied transaction IDs are bound to user, game, title, description and coins.
  Identical retries return the original result; different inputs return 409.
  Historical receipts without a replayable result return reconciliation-required
  409 without another charge. Calls without an ID still create a fresh purchase;
  callers must retain the same ID for uncertain retries. IDs must be valid single
  Firestore document IDs. Post-commit activity errors are logged without changing
  a confirmed purchase into a failure; activity delivery is best effort.
- Wallet initialization, top-ups and general spending: read current wallet and
  update histories in the same transaction. Group membership joins the spend.
  General spending rejects nonpositive/noninteger amounts.
- Store and group passes: price and wallet reads, debit and inventory/membership
  writes share a transaction. Stored prices must be nonnegative integers.
  Missing balance uses the existing 200-coin precheck default consistently,
  fixing the old increment behavior that could instead produce a negative value.
- Tips: reread both wallets in the transaction. Self-tips preserve money and
  report the unchanged balance; tip-history behavior remains.
- Voice charge: transactional debit helper, retaining its default zero and
  existing errors. Model and audio provider calls remain outside the transaction.
- Monthly subscription reward: transaction rechecks subscription status and
  expected renewal date, credits and advances date once under concurrent runs.
- Profile creation uses create-only writes. Repeated signup of an existing UID
  returns 409 instead of replacing a wallet/profile.
- Separate agent creator reward uses an atomic increment instead of an absolute
  balance computed before the write. Existing referral and rare-offer credits
  already use increments and are unchanged.

## Executed checks

```sh
python inzoneapi/scripts/test_offer_checkout_emulator.py /path/to/cloud-firestore-emulator.jar test_wallet_compatibility.py
PYTHONPATH=inzoneapi python -m unittest discover -s inzoneapi/tests -p test_game_offers.py -v
```

The compatibility suite contains the 14 checkout regressions plus 16 mixed-wallet
checks. It exercises real Firestore emulator transactions, including insufficient
funds races, same-ID retries, rollback, combined receipts/revenue, concurrent
credits/debits, duplicate renewal and profile reset prevention. Flask service and
store handlers execute against the emulator with dependency startup substituted.
Voice, renewal and profile checks exercise their persistence helpers; external
providers and the full application startup are not exercised. The separate agent
reward change is source-reviewed and syntax-checked, not model-runtime tested.

## Limits and next integration

Both checkout activation flags remain off. This PR does not establish deployed
Firestore rules, live authentication or universal wallet-writer coverage outside
this checkout. It does not add receipt verification/idempotency to legacy top-ups,
provider-verification security, refunds, or once-only reward issuance to existing
referral/rare-offer/creator rewards. Those authorization and economic guarantees
must not be inferred from concurrency tests. Legacy routes retain their existing
identity handling; new checkout continues to use verified Firebase tokens.

After review, the next product change is the trusted web-host purchase confirmation
and SDK offer interface using the existing catalog/checkout/inventory endpoints.
Reuse existing authentication and save/load. Keep tokens out of game iframes;
retain request IDs across retries and recover receipts before requesting a fresh
purchase. Activation still requires deployed writer/rules verification and a
production-equivalent browser test.
