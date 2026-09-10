# @inzone/checkout-host-client 0.1.0-preview.1

Dependency-free ESM adapter for the **trusted web host**, matching the backend
routes merged in PR #9. This is one SDK component, not the iframe SDK or a complete
release. Private package; not published to npm. The frontend agent should copy this
small package from its reviewed GitHub commit into the frontend repository (preserve
its version/tests) or use a local package dependency, not guess an npm package exists.

```js
import { createCheckoutClient } from './index.js';
const client = createCheckoutClient({
  baseUrl: configuredBackendOrigin, // HTTPS origin, no path/query/credentials
  gameId: hostLoadedGame.id,
  getToken: async () => {
    // Bind this client to the account that opened checkout; reject on account change.
    if (auth.currentUser?.uid !== checkoutAccountUid) return null;
    return auth.currentUser.getIdToken();
  }
});
const catalog = await client.getCatalog();
// Host renders server title, coins, currency and quantity and obtains confirmation.
// Persist {offerId,catalogVersion,requestId} under account+game BEFORE dispatch.
const receipt = await client.purchase(persistedConfirmedRequest);
// If outcome is uncertain, recover this request; do not mint a new request ID.
const recovered = await client.getReceipt(persistedConfirmedRequest.requestId);
const current = await client.getInventory(receipt.offerId);
```

The host owns confirmation, persistence, account/game binding, trusted response
rendering and iframe isolation. Never pass this client or token callback into game
code. The adapter does not enforce confirmation and must not be directly exposed
as an untrusted game's purchase primitive. Owner catalog publishing is intentionally
not a player-client method.

- Every authenticated call obtains a fresh token through the callback. Catalog is
  public and does not obtain/send a token. No cookies, redirects or cached responses.
- Purchase requires all three binding fields; rejects extra client-supplied fields.
  No generated request IDs, automatic retries, token logs or persistence here.
- Default 15s timeout covers token retrieval, fetch and response reading. Optional
  AbortSignal handles teardown. Canceling an HTTP request does not undo a charge.
- Errors expose code, status and outcomeUnknown. Network/timeout/invalid responses
  after a POST may have committed; recover the original ID. A 5xx is conservative
  unknown, not proof of rollback. A failed receipt lookup due to transport is not
  proof that no purchase exists. OFFER_CHANGED requires fresh catalog and renewed
  confirmation. CHECKOUT_DISABLED means the deployment has not enabled the routes.
- A successful response is unwrapped after envelope/object validation. Types describe
  the owning backend contract; this adapter is not a full response-schema validator.
  The host must not render arbitrary response text as HTML or trust game-supplied data.
- Replayed receipt balance/entitlement is historical. Read inventory for current state;
  deduplicate transaction IDs before granting effects. No consuming-units endpoint.

Run `npm test --prefix packages/checkout-host-client` with Node 18+.
Tests use injected HTTP responses to prove transport/error behavior. They do not
prove browser CORS, live Firebase auth, iframe isolation or a deployed backend.
Type declarations accompany the ESM implementation. Loopback HTTP origins are
accepted for local tests; external origins require HTTPS. Backend routing must be
configured explicitly; the client never guesses URLs or accepts them from a game.

Next: frontend host confirmation/iframe SDK integration described in
inzonesm/inzone-games, docs/handoff/WEB_SDK_HANDOFF.md. Both backend checkout flags
remain off pending release checks. No save/load, auth provider or backend economic
logic changed by this package.
