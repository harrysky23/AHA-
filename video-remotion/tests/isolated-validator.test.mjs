import assert from 'node:assert/strict';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {test} from 'node:test';
import {validate} from '../isolated/validate.mjs';

function check(source) {
  const directory = mkdtempSync(join(import.meta.dirname, '.validator-'));
  const file = join(directory, 'visual.tsx');
  try {
    writeFileSync(file, source);
    validate(file);
  } finally {
    rmSync(directory, {recursive: true});
  }
}

test('local SVG helpers work and use the same validation as Visual', () => {
  const visual = `export default function Visual(p: {progress: number}) {
    return <svg><Box x={p.progress * 10}/></svg>;
  }`;
  const helper = `const Box = ({x}: {x: number}) => <rect x={x} width={12} height={12}/>;`;
  check(helper + visual);
  assert.throws(() => check(helper.replace('<rect', '<image') + visual), /Unsupported element/);
  assert.throws(() => check(visual.replace('<Box x=', '<p.Box x=')), /Unsupported element/);
});
