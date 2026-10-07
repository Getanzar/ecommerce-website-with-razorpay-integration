const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

test('kids selector covers birth through fifteen in consecutive year bands', () => {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/kidsAges.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, { exports });
  const options = exports.KIDS_AGE_OPTIONS;
  assert.equal(options.length, 15);
  options.forEach(([value, label], age) => {
    assert.equal(value, `${age}-${age + 1}`);
    assert.equal(label, `${age}–${age + 1} ${age === 0 ? 'Year' : 'Years'}`);
  });
});
