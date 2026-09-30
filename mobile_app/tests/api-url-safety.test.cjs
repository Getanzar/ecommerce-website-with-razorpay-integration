const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function loadSafetyModule() {
  const exports = {};
  const code = ts.transpileModule(
    fs.readFileSync('src/apiUrlSafety.ts', 'utf8'),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText;

  vm.runInNewContext(code, { exports, URL, Error });
  return exports;
}

test('production accepts public HTTPS API URL', () => {
  const { assertSafeProductionApiUrl } = loadSafetyModule();

  assert.doesNotThrow(() =>
    assertSafeProductionApiUrl(
      'https://ziyamart.in/api/v1',
      true,
    ),
  );
});

test('production rejects insecure HTTP API URL', () => {
  const { assertSafeProductionApiUrl } = loadSafetyModule();

  assert.throws(
    () =>
      assertSafeProductionApiUrl(
        'http://example.com/api/v1',
        true,
      ),
    /HTTPS API URL/,
  );
});

test('production rejects localhost and private network API URLs', () => {
  const { assertSafeProductionApiUrl } = loadSafetyModule();

  const unsafeUrls = [
    'https://localhost:8000/api/v1',
    'https://127.0.0.1:8000/api/v1',
    'https://10.208.105.95:8000/api/v1',
    'https://192.168.1.20:8000/api/v1',
    'https://172.16.0.1:8000/api/v1',
    'https://172.31.255.255:8000/api/v1',
  ];

  for (const url of unsafeUrls) {
    assert.throws(
      () => assertSafeProductionApiUrl(url, true),
      /localhost or private-network/,
    );
  }
});

test('development allows local HTTP API URL', () => {
  const { assertSafeProductionApiUrl } = loadSafetyModule();

  assert.doesNotThrow(() =>
    assertSafeProductionApiUrl(
      'http://10.208.105.95:8000/api/v1',
      false,
    ),
  );
});
