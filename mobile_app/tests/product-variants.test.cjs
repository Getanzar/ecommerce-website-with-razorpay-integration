const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const exportsObject = {};
const code = ts.transpileModule(fs.readFileSync('src/ProductVariantsForm.tsx', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2022 },
}).outputText;
vm.runInNewContext(code, { exports: exportsObject, require: name => name === 'react-native' ? { StyleSheet: { create: value => value } } : {} });
const { validateVariants } = exportsObject;

test('multiple sizes share a color with independent whole-number stock', () => {
  assert.equal(validateVariants([{ color: 'Blue', size: 'M', stock: '0' }, { color: 'Blue', size: 'L', stock: '12' }]), '');
});

test('case and whitespace cannot create duplicate color-size rows', () => {
  assert.match(validateVariants([{ color: 'Blue', size: 'M', stock: '5' }, { color: ' blue ', size: 'm', stock: '2' }]), /already exists/);
});

test('missing and invalid variant values are caught before upload', () => {
  for (const stock of ['', '-1', '1.5', '1000001']) assert.match(validateVariants([{ color: 'Red', size: 'M', stock }]), /whole number/);
  assert.match(validateVariants([{ color: ' ', size: 'M', stock: '1' }]), /both color and size/);
  assert.match(validateVariants([]), /between 1 and 100/);
});
