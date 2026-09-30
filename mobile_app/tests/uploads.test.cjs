const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(filename, mocks = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports, require: name => mocks[name], Blob, Uint8Array, TextEncoder, Math });
  return exports;
}

// Exercise the installed SDK encoder: the previous tests never encoded photo parts.
const expoRoot = path.dirname(require.resolve('expo/package.json'));
const { convertFormDataAsync } = load(path.join(expoRoot, 'src/winter/fetch/convertFormData.ts'), {
  '../../utils/blobUtils': { blobToArrayBufferAsync: blob => blob.arrayBuffer() },
});
class Parts {
  rows = [];
  append(name, value) { this.rows.push([name, value]); }
  entries() { return this.rows.values(); }
}
class LocalFile {
  constructor(uri) {
    this.name = uri.split('/').pop();
    this.type = 'image/jpeg';
    this.exists = !uri.includes('missing');
    this.size = uri.includes('large') ? 9 * 1024 * 1024 : 4;
  }
  async bytes() { return new Uint8Array([255, 216, 255, 217]); }
}
const { appendPhoto } = load('src/uploads.ts', { 'expo-file-system': { File: LocalFile } });

test('Expo 57 reproduces the old URI upload failure before sending the request', async () => {
  const form = new Parts();
  form.append('image', { uri: 'file:///front.jpg', name: 'front.jpg', type: 'image/jpeg' });
  await assert.rejects(convertFormDataAsync(form, 'boundary'), /Unsupported FormDataPart implementation/);
});

test('front/back file bytes and variant fields encode using the actual Expo encoder', async () => {
  const form = new Parts();
  appendPhoto(form, 'image', { uri: 'file:///front.jpg' });
  appendPhoto(form, 'back_image', { uri: 'file:///back.jpg' });
  form.append('variants', JSON.stringify([{ color: 'Blue', size: 'M', stock: 3 }]));
  const { body, boundary } = await convertFormDataAsync(form, 'upload-test');
  const text = new TextDecoder().decode(body);
  assert.equal(boundary, 'upload-test');
  assert.match(text, /name="image"; filename="front.jpg"/);
  assert.match(text, /name="back_image"; filename="back.jpg"/);
  assert.match(text, /content-type: image\/jpeg/);
  assert.match(text, /"color":"Blue","size":"M","stock":3/);
  assert.equal(Buffer.from(body).toString('hex').split('ffd8ffd9').length - 1, 2);
});

test('missing and oversized photos fail before the network call', () => {
  assert.throws(() => appendPhoto(new Parts(), 'image', { uri: 'file:///missing.jpg' }), /Select it again/);
  assert.throws(() => appendPhoto(new Parts(), 'image', { uri: 'file:///large.jpg' }), /smaller than 8 MB/);
});
