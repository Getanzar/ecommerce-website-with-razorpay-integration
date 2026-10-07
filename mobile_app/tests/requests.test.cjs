const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

test('401 identifies the rejected session so stale requests cannot log out a newer login', async () => {
  const client = api(async () => ({ ok: false, status: 401, json: async () => ({ detail: 'Expired' }) }));
  let currentToken = 'new-session';
  client.setUnauthorizedHandler(failedToken => {
    if (failedToken === currentToken) currentToken = null;
  });
  await assert.rejects(client.request('/cart/', {}, 'old-session'), /Expired/);
  assert.equal(currentToken, 'new-session');
  await assert.rejects(client.request('/cart/', {}, 'new-session'), /Expired/);
  assert.equal(currentToken, null);
});

test('temporary server errors do not invalidate a session', async () => {
  const client = api(async () => ({ ok: false, status: 503, json: async () => ({ detail: 'Unavailable' }) }));
  let expired = false;
  client.setUnauthorizedHandler(() => { expired = true; });
  await assert.rejects(client.request('/cart/', {}, 'session'), /Unavailable/);
  assert.equal(expired, false);
});

function api(fetchWithRetry) {
  const exports = {};
  const mocks = { './retry': { fetchWithRetry }, './telemetry': { reportError() {} }, 'expo-device': {}, './apiUrlSafety': { assertSafeProductionApiUrl() {} } };
  const code = ts.transpileModule(fs.readFileSync('src/api.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports, require: name => mocks[name], process: { env: {} }, FormData, fetch, Error, URLSearchParams });
  return exports;
}

test('seller multipart upload gets two minutes and leaves boundary to native fetch', async () => {
  let calls = 0;
  const client = api(async (url, options, fetcher, timeout) => {
    calls++;
    assert.equal(timeout, 120000);
    assert.equal(options.headers['Content-Type'], undefined);
    assert.equal(options.headers.Authorization, 'Token token');
    assert.ok(options.body instanceof FormData);
    return { ok: true, status: 200, json: async () => ({ message: 'Saved' }) };
  });
  await client.request('/partners/seller/grocery/products/new/', { method: 'POST', body: new FormData() }, 'token');
  assert.equal(calls, 1);
});

test('ordinary saves get a minute; reads remain bounded at thirty seconds', async () => {
  const deadlines = [];
  const client = api(async (_, options, fetcher, timeout) => {
    deadlines.push(timeout);
    return { ok: true, status: 200, json: async () => ({}) };
  });
  await client.request('/partners/seller/grocery/availability/', { method: 'PATCH', body: '{}' });
  await client.request('/products/');
  assert.deepEqual(deadlines, [60000, 30000]);
});

test('ambiguous seller upload advises checking saved data without repeating request', async () => {
  let calls = 0;
  const client = api(async () => { calls++; const error = new Error(); error.name = 'TimeoutError'; throw error; });
  await assert.rejects(client.request('/partners/seller/grocery/products/new/', { method: 'POST', body: new FormData() }), /server took too long.*Reopen the catalog/);
  assert.equal(calls, 1);
});

test('checkout network errors still direct the customer to saved orders', async () => {
  const client = api(async () => { throw new Error('offline'); });
  await assert.rejects(client.request('/checkout/shop/', { method: 'POST' }), /Check Orders before submitting again/);
});

test('authentication throttling exposes the server cooldown without replaying the write', async () => {
  let calls = 0;
  const client = api(async () => {
    calls++;
    return { ok: false, status: 429, headers: { get: () => '60' }, json: async () => ({ detail: 'Please wait.' }) };
  });
  await assert.rejects(client.resendSignupOtp('buyer@example.com'), error => error.retryAfter === 60 && error.message === 'Please wait.');
  assert.equal(calls, 1);
});
