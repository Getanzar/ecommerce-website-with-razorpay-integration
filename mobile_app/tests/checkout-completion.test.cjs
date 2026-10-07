const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function load(payOrder) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync('src/checkoutCompletion.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports, require: () => ({ payOrder }) });
  return exports.completePlacedOrder;
}
const order = { id: 7, kind: 'shop', payment_method: 'online', payment_status: 'Pending' };

test('saved order reaches payment before cart refresh and survives refresh failure', async () => {
  const calls = [];
  const complete = load(async (token, saved) => {
    calls.push('payment');
    assert.equal(token, 'session');
    assert.equal(saved.id, 7);
    return { ...saved, payment_status: 'Paid' };
  });
  const result = await complete('session', order, async () => { calls.push('refresh'); throw new Error('Cart unavailable'); });
  assert.equal(result.payment_status, 'Paid');
  assert.deepEqual(calls, ['payment', 'refresh']);
});

test('payment recovery instruction is retained when cart refresh also fails', async () => {
  const complete = load(async () => { throw new Error('Order #7 saved; check payment in Orders'); });
  await assert.rejects(complete('session', order, async () => { throw new Error('Cart unavailable'); }), /Order #7 saved/);
});

test('COD confirms its existing order without invoking Razorpay', async () => {
  let refreshed = false;
  const complete = load(async () => { assert.fail('Razorpay must not open for COD'); });
  const result = await complete('session', { ...order, payment_method: 'cod' }, async () => { refreshed = true; });
  assert.equal(result.id, 7);
  assert.equal(result.payment_method, 'cod');
  assert.equal(refreshed, true);
});
