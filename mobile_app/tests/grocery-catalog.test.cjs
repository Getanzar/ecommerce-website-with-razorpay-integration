const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const loaded = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/groceryCatalog.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports: loaded, Error });
const { createStoreCatalog } = loaded;

test('nearby store pagination stops finished stores and keeps combined counts', async () => {
  const calls = [];
  const fetch = createStoreCatalog(['nearby-a', 'nearby-b'], async (store, page) => {
    calls.push(`${store}:${page}`);
    return { items: [{ id: `${store}:${page}` }], count: store === 'nearby-a' ? 1 : 2, hasNext: store === 'nearby-b' && page === 1 };
  });
  const signal = new AbortController().signal;
  const first = await fetch(1, signal);
  assert.equal(first.items.length, 2);
  assert.equal(first.count, 3);
  assert.equal(first.hasNext, true);
  const second = await fetch(2, signal);
  assert.equal(second.items.length, 1);
  assert.equal(second.count, 3);
  assert.equal(second.hasNext, false);
  assert.deepEqual(calls, ['nearby-a:1', 'nearby-b:1', 'nearby-b:2']);
  await fetch(1, signal);
  assert.deepEqual(calls.slice(-2), ['nearby-a:1', 'nearby-b:1']);
});

test('partial store failure retries every unfinished store without skipping a page', async () => {
  const calls = [];
  let fail = true;
  const fetch = createStoreCatalog(['a', 'b'], async (store, page) => {
    calls.push(`${store}:${page}`);
    if (store === 'b' && page === 2 && fail) { fail = false; throw new Error('offline'); }
    return { items: [{ id: `${store}:${page}` }], count: 2, hasNext: page === 1 };
  });
  const signal = new AbortController().signal;
  await fetch(1, signal);
  await assert.rejects(fetch(2, signal), /offline/);
  const retry = await fetch(2, signal);
  assert.equal(retry.items.length, 2);
  assert.deepEqual(calls, ['a:1', 'b:1', 'a:2', 'b:2', 'a:2', 'b:2']);
});

test('cancelled category requests do not advance store pagination', async () => {
  const controller = new AbortController();
  const fetch = createStoreCatalog(['a'], async () => {
    controller.abort();
    return { items: [], count: 0, hasNext: false };
  });
  await assert.rejects(fetch(1, controller.signal), /cancelled/);
});
