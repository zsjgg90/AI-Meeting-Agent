const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const sourcePath = path.join(__dirname, '..', 'src', 'utils', 'numberedList.ts');
const source = fs.readFileSync(sourcePath, 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
});

const moduleShim = { exports: {} };
Function('exports', 'require', 'module', '__filename', '__dirname', output.outputText)(
  moduleShim.exports,
  require,
  moduleShim,
  sourcePath,
  path.dirname(sourcePath),
);

const { normalizeNumberedListItems } = moduleShim.exports;

function expectItems(name, input, expected) {
  assert.deepEqual(normalizeNumberedListItems(input), expected, name);
}

expectItems('array input is preserved as independent rows', ['内容A', '内容B'], ['内容A', '内容B']);
expectItems('numbered semicolon string is split', '1. 内容A；2. 内容B；3. 内容C', ['内容A', '内容B', '内容C']);
expectItems('numbered multiline string is split', '1、内容A\n2、内容B\n3、内容C', ['内容A', '内容B', '内容C']);
expectItems('single item is kept', '只有一条内容', ['只有一条内容']);
expectItems('empty content is removed', ['', null, undefined, '  '], []);
expectItems('normal periods are not split', 'V3.2版本上线。P0功能100%交付。', ['V3.2版本上线。P0功能100%交付。']);
expectItems('leading numbering is stripped', ['1. 内容A', '2、内容B'], ['内容A', '内容B']);

for (const item of normalizeNumberedListItems('1. 内容A；2. 内容B')) {
  assert.equal(/^\d+\s*[.、]/.test(item), false, `number marker should be stripped from ${item}`);
}

console.log('numbered list formatter tests passed');
