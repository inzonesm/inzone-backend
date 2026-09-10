/** Trusted-host HTTP adapter. Never install this authenticated client in a game. */
export class CheckoutClientError extends Error {
  constructor(code, { status = 0, outcomeUnknown = false } = {}) {
    super(code);
    this.name = 'CheckoutClientError';
    this.code = code;
    this.status = status;
    this.outcomeUnknown = outcomeUnknown;
  }
}

const validId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
function identifier(value) {
  if (!validId(value)) throw new CheckoutClientError('INVALID_IDENTIFIER');
  return value;
}

export function createCheckoutClient({ baseUrl, gameId, getToken, fetch: fetcher = globalThis.fetch, timeoutMs = 15000 }) {
  identifier(gameId);
  let url;
  try { url = new URL(baseUrl); } catch { throw new CheckoutClientError('INVALID_BASE_URL'); }
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) ||
      url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new CheckoutClientError('INVALID_BASE_URL');
  }
  if (typeof getToken !== 'function' || typeof fetcher !== 'function' ||
      !Number.isFinite(timeoutMs) || timeoutMs < 1 || timeoutMs > 120000) {
    throw new CheckoutClientError('INVALID_CLIENT_OPTIONS');
  }
  const prefix = `${url.origin}/api/game-sdk/v2/games/${gameId}`;

  async function call(path, { body, authenticated = true, signal } = {}) {
    const controller = new AbortController();
    let sent = false;
    let timer;
    let abortListener;
    const outcomeUnknown = () => body !== undefined && sent;
    const abort = () => controller.abort();
    if (signal?.aborted) throw new CheckoutClientError('REQUEST_ABORTED');
    signal?.addEventListener('abort', abort, { once: true });
    const interrupted = new Promise((_, reject) => {
      abortListener = () => reject(new CheckoutClientError('REQUEST_ABORTED', { outcomeUnknown: outcomeUnknown() }));
      controller.signal.addEventListener('abort', abortListener, { once: true });
      timer = setTimeout(() => {
        // Reject with TIMEOUT before aborting the underlying fetch.
        reject(new CheckoutClientError('REQUEST_TIMEOUT', { outcomeUnknown: outcomeUnknown() }));
        controller.abort();
      }, timeoutMs);
    });
    const operation = (async () => {
      const headers = { Accept: 'application/json' };
      if (authenticated) {
        let token;
        try { token = await getToken(); }
        catch { throw new CheckoutClientError('AUTH_UNAVAILABLE'); }
        if (controller.signal.aborted) throw new CheckoutClientError('REQUEST_ABORTED');
        if (typeof token !== 'string' || !token.trim()) throw new CheckoutClientError('UNAUTHENTICATED');
        headers.Authorization = `Bearer ${token}`;
      }
      if (controller.signal.aborted) throw new CheckoutClientError('REQUEST_ABORTED');
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      let response;
      sent = true;
      try {
        response = await fetcher(prefix + path, {
          method: body === undefined ? 'GET' : 'POST', headers,
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
          signal: controller.signal, credentials: 'omit', redirect: 'error', cache: 'no-store'
        });
      } catch {
        throw new CheckoutClientError('NETWORK_ERROR', { outcomeUnknown: outcomeUnknown() });
      }
      let envelope;
      try { envelope = await response.json(); }
      catch { throw new CheckoutClientError('INVALID_RESPONSE', { status: response.status, outcomeUnknown: outcomeUnknown() }); }
      if (!response.ok || envelope?.success !== true) {
        const code = typeof envelope?.code === 'string' && /^[A-Z0-9_]{1,100}$/.test(envelope.code)
          ? envelope.code : 'CHECKOUT_UNAVAILABLE';
        throw new CheckoutClientError(code, {
          status: response.status,
          // Conservatively recover POSTs on server failures or inconsistent success envelopes.
          outcomeUnknown: outcomeUnknown() && (response.status >= 500 || response.ok)
        });
      }
      if (!object(envelope.data)) throw new CheckoutClientError('INVALID_RESPONSE', {
        status: response.status, outcomeUnknown: outcomeUnknown()
      });
      return envelope.data;
    })();
    try { return await Promise.race([operation, interrupted]); }
    finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      controller.signal.removeEventListener('abort', abortListener);
    }
  }

  return Object.freeze({
    getCatalog(options = {}) { return call('/catalog', { signal: options.signal, authenticated: false }); },
    purchase(input, options = {}) {
      if (!object(input) || Object.keys(input).sort().join(',') !== 'catalogVersion,offerId,requestId') {
        throw new CheckoutClientError('INVALID_REQUEST');
      }
      const body = { offerId: identifier(input.offerId), catalogVersion: identifier(input.catalogVersion), requestId: identifier(input.requestId) };
      return call('/purchases', { body, signal: options.signal });
    },
    getReceipt(requestId, options = {}) { return call('/purchases/' + identifier(requestId), { signal: options.signal }); },
    getInventory(offerId, options = {}) { return call('/inventory/' + identifier(offerId), { signal: options.signal }); }
  });
}
