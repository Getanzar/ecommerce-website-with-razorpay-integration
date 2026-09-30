const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function setup({ status = 200, foreground = true } = {}) {
  const state = { stored: JSON.stringify({ job: 12, token: 'device-token', until: Date.now() + 60000 }), stopped: 0, uploads: [], handler: null };
  const modules = {
    'expo-task-manager': { defineTask: (_, handler) => { state.handler = handler; } },
    'expo-location': {
      Accuracy: { High: 4 }, hasStartedLocationUpdatesAsync: async () => true,
      stopLocationUpdatesAsync: async () => { state.stopped++; },
      requestForegroundPermissionsAsync: async () => ({ granted: foreground }),
      requestBackgroundPermissionsAsync: async () => ({ granted: true }),
      startLocationUpdatesAsync: async () => {},
    },
    'expo-secure-store': { getItemAsync: async () => state.stored, deleteItemAsync: async () => { state.stored = null; }, setItemAsync: async (_, value) => { state.stored = value; } },
    './api': { API_URL: 'https://example.test/api/v1' }, './telemetry': { reportError() {} },
  };
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync('src/backgroundTracking.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, { exports, require: name => modules[name], Date, Error, AbortSignal, fetch: async (url, options) => { state.uploads.push({ url, options }); return { status }; } });
  return { state, api: exports };
}
const fix = (timestamp = Date.now()) => ({ timestamp, coords: { latitude: 28.123456, longitude: 77.123456, accuracy: 5 } });
test('revoked job access clears tracking credentials and stops the native task', async () => {
  const { state } = setup({ status: 403 });
  await state.handler({ data: { locations: [fix()] } });
  assert.equal(state.stored, null); assert.equal(state.stopped, 1);
});
test('stale location is never uploaded as current', async () => {
  const { state } = setup();
  await state.handler({ data: { locations: [fix(Date.now() - 180000)] } });
  assert.equal(state.uploads.length, 0);
});
test('expired tracking stops without sending coordinates', async () => {
  const { state } = setup(); state.stored = JSON.stringify({ job: 12, token: 'old', until: Date.now() - 100 });
  await state.handler({ data: { locations: [fix()] } });
  assert.equal(state.uploads.length, 0); assert.equal(state.stored, null);
});
test('denied permission never starts a replacement tracking session', async () => {
  const { state, api } = setup({ foreground: false }); const previous = state.stored;
  await assert.rejects(api.startTracking('new-token', 30), /permission was denied/);
  assert.equal(state.stored, previous);
});
test('only the latest fix is uploaded with the scoped device credential', async () => {
  const { state } = setup();
  await state.handler({ data: { locations: [fix(Date.now() - 10000), fix()] } });
  assert.equal(state.uploads.length, 1);
  assert.match(state.uploads[0].url, /jobs\/12\/location/);
  assert.equal(state.uploads[0].options.headers.Authorization, 'Token device-token');
});
