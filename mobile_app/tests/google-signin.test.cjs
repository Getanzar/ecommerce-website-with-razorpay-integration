const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const crypto = require('node:crypto');

function client({ stateMismatch = false, cancelled = false, error = '', hostileUrl = false } = {}) {
  const exports = {};
  const calls = [];
  let state;
  const mocks = {
    'expo-crypto': {
      getRandomBytesAsync: async size => crypto.randomBytes(size),
      CryptoDigestAlgorithm: { SHA256: 'sha256' }, CryptoEncoding: { BASE64: 'base64' },
      digestStringAsync: async (_, value) => crypto.createHash('sha256').update(value).digest('base64'),
    },
    'expo-device': { modelName: 'Test phone' },
    'expo-web-browser': { openAuthSessionAsync: async (_, redirect) => {
      assert.equal(redirect, 'ziyamart://auth/callback');
      if (cancelled) return { type: 'cancel' };
      return { type: 'success', url: `ziyamart://auth/callback?${new URLSearchParams({ state: stateMismatch ? 'wrong' : state, ...(error ? { error } : { code: 'one-use-code' }) })}` };
    } },
    './api': { API_URL: 'https://www.ziyamart.in/api/v1', request: async (path, options, token) => {
      const body = JSON.parse(options.body); calls.push({ path, body, token });
      if (path.endsWith('/start/')) { state = body.state; return { url: hostileUrl ? 'https://evil.example/api/v1/auth/google/browser/?ticket=1' : 'https://www.ziyamart.in/api/v1/auth/google/browser/?ticket=1' }; }
      return { token: 'session-token', user: { id: 1 } };
    } },
  };
  const code = ts.transpileModule(fs.readFileSync('src/googleSignIn.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, { exports, require: name => { if (!mocks[name]) throw Error(name); return mocks[name]; }, URL, Error });
  return { ...exports, calls };
}

test('Google handoff uses secure PKCE, binds state, and exchanges code without Google credentials', async () => {
  const app = client();
  const result = await app.googleSignIn();
  assert.equal(result.token, 'session-token');
  assert.equal(app.calls.length, 2);
  assert.equal(app.calls[0].token, undefined);
  assert.match(app.calls[0].body.state, /^[a-f0-9]{64}$/);
  assert.match(app.calls[1].body.verifier, /^[a-f0-9]{64}$/);
  assert.equal(app.calls[0].body.challenge, crypto.createHash('sha256').update(app.calls[1].body.verifier).digest('base64url'));
  assert.equal(app.calls[1].body.code, 'one-use-code');
  assert.equal(app.calls[1].token, undefined);
});
test('connecting Google keeps the existing authenticated device session', async () => {
  const app = client();
  const result = await app.googleSignIn('existing-session');
  assert.equal(result.token, 'existing-session');
  assert.equal(app.calls[0].token, 'existing-session');
  assert.equal(app.calls[1].token, 'existing-session');
});
test('Google rejects a callback with mismatched state before exchanging code', async () => {
  const app = client({ stateMismatch: true });
  await assert.rejects(app.googleSignIn(), /could not be verified/);
  assert.equal(app.calls.length, 1);
});
test('Google cancellation does not create a mobile session', async () => {
  const app = client({ cancelled: true });
  assert.equal(await app.googleSignIn(), null);
  assert.equal(app.calls.length, 1);
});
test('Google server error returns a useful message without exchanging code', async () => {
  const app = client({ error: 'Connect Google from your profile first.' });
  await assert.rejects(app.googleSignIn(), /Connect Google/);
  assert.equal(app.calls.length, 1);
});
test('Google refuses an authentication page outside the configured backend', async () => {
  const app = client({ hostileUrl: true });
  await assert.rejects(app.googleSignIn(), /Invalid Google sign-in destination/);
});
