const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const exportsObject = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/catalogPaging.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports: exportsObject, AbortController, Error });
const { CatalogPager, catalogPage } = exportsObject;

test('pagination metadata and legacy array responses are both understood', () => {
  assert.equal(catalogPage([{ id: 1 }]).hasNext, false);
  const page = catalogPage({ results: [{ id: 1 }], count: 60, next: '/products/?page=2' });
  assert.equal(page.hasNext, true);
  assert.equal(page.count, 60);
});

test('later-page failure keeps products and retries the same page without duplicate rows', async () => {
  let fail = true;
  const pages = [];
  const pager = new CatalogPager(async page => {
    pages.push(page);
    if (page === 2 && fail) { fail = false; throw new Error('offline'); }
    return { items: page === 1 ? [{ id: 1 }] : [{ id: 1 }, { id: 2 }], hasNext: page === 1, count: 2 };
  });
  await pager.refresh();
  await pager.more();
  assert.equal(pager.state.items.length, 1);
  assert.equal(pager.state.error, 'offline');
  await pager.more();
  assert.equal(pager.state.items.length, 2);
  assert.equal(pager.state.error, '');
  await pager.more();
  assert.deepEqual(pages, [1, 2, 2]);
});

test('refresh discards a stale response even if transport ignores cancellation', async () => {
  let resolveOld;
  let calls = 0;
  const pager = new CatalogPager(() => ++calls === 1 ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve({ items: [{ id: 2 }], hasNext: false, count: 1 }));
  const old = pager.refresh();
  await pager.refresh();
  resolveOld({ items: [{ id: 1 }], hasNext: true, count: 10 });
  await old;
  assert.equal(pager.state.items[0].id, 2);
  assert.equal(pager.state.count, 1);
});

test('repeated load-more taps send only one request and disposal aborts it', async () => {
  let finish, signal, calls = 0;
  const pager = new CatalogPager((page, currentSignal) => {
    calls++; signal = currentSignal;
    return page === 1 ? Promise.resolve({ items: [{ id: 1 }], hasNext: true, count: 2 }) : new Promise(resolve => { finish = resolve; });
  });
  await pager.refresh();
  const pending = pager.more();
  await pager.more();
  assert.equal(calls, 2);
  pager.dispose();
  assert.equal(signal.aborted, true);
  finish({ items: [{ id: 2 }], hasNext: false, count: 2 });
  await pending;
  assert.equal(pager.state.items.length, 1);
});
