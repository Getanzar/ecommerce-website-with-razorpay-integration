const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
function load(path, mocks) {
  const code = ts.transpileModule(fs.readFileSync(path, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: name => mocks[name], Error, setTimeout: fn => { fn(); }, AbortSignal, fetch });
  return exports;
}
const pending = { id: 7, kind: 'shop', payment_status: 'Pending', payment_method: 'online', razorpay: { key_id: 'key', order_id: 'order', amount: 10000, currency: 'INR', name: 'Shop' } };
test('captured recovery never opens checkout twice', async () => {
  let opened = false;
  const api = load('src/nativePayments.ts', { './api': { request: async () => ({ ...pending, payment_status: 'Paid' }) }, 'react-native-razorpay': { open: async () => { opened = true; } } });
  assert.equal((await api.payOrder('token', pending)).payment_status, 'Paid'); assert.equal(opened, false);
});
test('native result is verified on the server', async () => {
  const calls = [];
  const api = load('src/nativePayments.ts', { './api': { request: async (path, options) => { const body = JSON.parse(options.body); calls.push(body); return { ...pending, payment_status: body.action === 'verify' ? 'Paid' : 'Pending' }; } }, 'react-native-razorpay': { open: async () => ({ razorpay_payment_id: 'pay', razorpay_signature: 'sig', razorpay_order_id: 'order' }) } });
  await api.payOrder('token', pending); assert.equal(calls[1].action, 'verify'); assert.equal(calls[1].razorpay_signature, 'sig');
});
test('cancelled checkout preserves pending order', async () => {
  const api = load('src/nativePayments.ts', { './api': { request: async () => pending }, 'react-native-razorpay': { open: async () => { throw { code: 2 }; } } });
  await assert.rejects(api.payOrder('token', pending), /Order #7 is saved/);
});
test('lost verification response tells customer to check saved order', async () => {
  const api = load('src/nativePayments.ts', { './api': { request: async (_, options) => { if (JSON.parse(options.body).action === 'verify') throw Error('offline'); return pending; } }, 'react-native-razorpay': { open: async () => ({}) } });
  await assert.rejects(api.payOrder('token', pending), /confirmation is pending/);
});
test('writes never retry after ambiguous network failure', async () => {
  const api = load('src/retry.ts', {}); let count = 0;
  await assert.rejects(api.fetchWithRetry('/checkout', { method: 'POST' }, async () => { count++; throw Error('offline'); })); assert.equal(count, 1);
});
test('transient read failures retry with a finite limit', async () => {
  const api = load('src/retry.ts', {}); let count = 0;
  await assert.rejects(api.fetchWithRetry('/orders', {}, async () => { count++; throw Error('offline'); })); assert.equal(count, 3);
});
