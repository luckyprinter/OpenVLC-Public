import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const requireFromReactPlugin = createRequire(require.resolve('@vitejs/plugin-react'));
const { parse } = requireFromReactPlugin('@babel/parser');
const upstream = process.argv[2];

if (!upstream || process.argv.length !== 3) {
  console.error('Usage: node scripts/verify-source.mjs <OpenVLC-Public Git checkout>');
  process.exit(2);
}

const repository = resolve(upstream);
const source = (name) => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8');
const academy = source('Academy.jsx');
const explorer = source('DeepDive.jsx');
const repoIndex = JSON.parse(source('data/repo-index.json'));

function git(...args) {
  return execFileSync('git', ['-C', repository, ...args], { maxBuffer: 16 * 1024 * 1024 });
}

function ast(text) {
  return parse(text, { sourceType: 'module', plugins: ['jsx'] });
}

function constants(tree) {
  return new Map(tree.program.body.flatMap((statement) => statement.type === 'VariableDeclaration'
    ? statement.declarations.filter((node) => node.id.type === 'Identifier').map((node) => [node.id.name, node.init])
    : []));
}

function staticString(node, bindings) {
  while (node?.type === 'Identifier') node = bindings.get(node.name);
  if (node?.type === 'TemplateLiteral' && node.expressions.length === 0) {
    return node.quasis[0].value.cooked;
  }
  return node?.type === 'StringLiteral' ? node.value : undefined;
}

const filesByRef = new Map();
const linesByBlob = new Map();
const errors = [];
let referenceCount = 0;
let excerptCount = 0;

function filesAt(ref) {
  if (!/^[a-f0-9]{40}$/.test(ref ?? '')) {
    throw new Error('Expected a full, immutable Git commit SHA, received ' + String(ref));
  }
  if (!filesByRef.has(ref)) {
    let tree;
    try {
      tree = git('ls-tree', '-rlz', ref).toString('utf8');
    } catch (error) {
      throw new Error('Pinned commit ' + ref + ' is unavailable in ' + repository, { cause: error });
    }
    const files = new Map();
    for (const entry of tree.split('\0').filter(Boolean)) {
      const [, blob, bytes, path] = entry.match(/^\d+ blob ([a-f0-9]+)\s+(\d+)\t(.+)$/s) ?? [];
      if (blob) files.set(path, { blob, bytes: Number(bytes) });
    }
    filesByRef.set(ref, files);
  }
  return filesByRef.get(ref);
}

function contentLines(blob) {
  if (!linesByBlob.has(blob)) {
    const text = git('cat-file', 'blob', blob).toString('utf8');
    const lines = text ? text.split(/\r?\n/) : [];
    if (lines.at(-1) === '') lines.pop();
    linesByBlob.set(blob, lines);
  }
  return linesByBlob.get(blob);
}

function checkRange(range, lineCount, context) {
  const match = String(range).trim().match(/^(\d+)(?:\s*[-–]\s*(\d+))?$/);
  if (!match) {
    errors.push(context + ' has unrecognized line range ' + JSON.stringify(range));
    return;
  }
  const start = Number(match[1]);
  const end = Number(match[2] ?? start);
  if (start < 1 || end < start || end > lineCount) {
    errors.push(context + ' requests lines ' + start + '–' + end + ' in a ' + lineCount + '-line file');
    return;
  }
  return { start, end };
}

function checkReference({ ref, path, ranges, excerpt, context }) {
  referenceCount++;
  const entry = filesAt(ref).get(path);
  if (!entry) {
    errors.push(context + ' points to missing path ' + path + ' at ' + ref);
    return;
  }
  const label = context + ' (' + path + ')';
  for (const range of ranges?.split(',') ?? []) {
    const lines = contentLines(entry.blob);
    const span = checkRange(range, lines.length, label);
    if (!span || !excerpt) continue;
    excerptCount++;
    const expected = lines.slice(span.start - 1, span.end);
    if (excerpt.length !== expected.length) {
      errors.push(label + ' contains ' + excerpt.length + ' excerpt lines for a ' + expected.length + '-line source span');
      continue;
    }
    const index = excerpt.findIndex((line, offset) => line.trimEnd() !== expected[offset].trimEnd());
    if (index !== -1) {
      errors.push(label + ' first excerpt mismatch at line ' + (span.start + index) +
        '\n  expected ' + JSON.stringify(expected[index]) + '\n  found    ' + JSON.stringify(excerpt[index]));
    }
  }
}

function walk(node, visit) {
  if (!node?.type) return;
  visit(node);
  for (const child of Object.values(node)) {
    if (Array.isArray(child)) child.forEach((item) => walk(item, visit));
    else walk(child, visit);
  }
}

function checkPage(text, filename, defaultRefName) {
  const tree = ast(text);
  const bindings = constants(tree);
  const defaultRef = staticString(bindings.get(defaultRefName), bindings);
  filesAt(defaultRef);

  walk(tree, (node) => {
    if (node.type !== 'ObjectExpression') return;
    const fields = new Map(node.properties.filter((property) => property.type === 'ObjectProperty' && !property.computed)
      .map((property) => [property.key.name ?? property.key.value, property.value]));
    const path = staticString(fields.get('path'), bindings) ?? staticString(fields.get('code'), bindings);
    if (!path) return;
    const ref = fields.has('ref') ? staticString(fields.get('ref'), bindings) : defaultRef;
    const lessonRange = staticString(fields.get('range'), bindings);
    const lines = fields.get('lines');
    const ranges = lessonRange ?? staticString(lines, bindings);
    const context = filename + ':' + node.loc.start.line;
    const excerpt = lines?.type === 'ArrayExpression'
      ? lines.elements.map((element) => staticString(element?.elements?.[0], bindings))
      : undefined;
    if (excerpt?.some((line) => line === undefined)) {
      errors.push(context + ' contains an unsupported excerpt line expression');
      return;
    }
    checkReference({ ref, path, ranges, excerpt, context });
  });

  return defaultRef;
}

try {
  if (!Array.isArray(repoIndex) || !repoIndex.length) throw new Error('Repository index must contain file entries');
  const explorerPin = checkPage(explorer, 'DeepDive.jsx', 'SOURCE_PIN');
  checkPage(academy, 'Academy.jsx', 'FW');

  const files = filesAt(explorerPin);
  const indexedPaths = new Set();
  for (const item of repoIndex) {
    const { path, blob, bytes, lineCount, symbols, headings } = item;
    if (indexedPaths.has(path)) errors.push('Duplicate repository-index path ' + path);
    indexedPaths.add(path);
    const actual = files.get(path);
    if (!actual) {
      errors.push('Repository index contains missing path ' + path);
      continue;
    }
    if (blob !== actual.blob) {
      errors.push('Repository index blob mismatch for ' + path + ': expected ' + actual.blob + ', found ' + blob);
    }
    if (bytes !== actual.bytes) {
      errors.push('Repository index size mismatch for ' + path + ': expected ' + actual.bytes + ', found ' + bytes);
    }
    if (lineCount !== null || symbols.length || headings.length) {
      const count = contentLines(actual.blob).length;
      if (lineCount !== null && lineCount !== count) {
        errors.push('Repository index line count mismatch for ' + path + ': expected ' + count + ', found ' + lineCount);
      }
      for (const { name, line, endLine } of symbols) checkRange(line + '-' + (endLine ?? line), count, path + ' symbol ' + name);
      for (const { title, line } of headings) checkRange(line, count, path + ' heading ' + title);
    }
  }
  for (const path of files.keys()) {
    if (!indexedPaths.has(path)) errors.push('Repository index omits pinned file ' + path);
  }
} catch (error) {
  console.error(error.message);
  process.exit(2);
}

if (errors.length) {
  console.error(errors.map((message) => '- ' + message).join('\n'));
  console.error('Source verification failed (' + errors.length + ' discrepancies).');
  process.exitCode = 1;
} else {
  console.log('Verified ' + repoIndex.length + ' indexed files, ' + referenceCount +
    ' source references, and ' + excerptCount + ' annotated excerpts against ' +
    filesByRef.size + ' pinned checkout snapshot(s).');
}
