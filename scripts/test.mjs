import { spawnSync } from 'node:child_process';

const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => key !== 'Path'));
for (const args of [
  ['node_modules/typescript/bin/tsc', '--noEmit'],
  ['node_modules/typescript/bin/tsc', '-p', 'electron/tsconfig.json', '--noEmit'],
  ['scripts/backend-test.mjs'],
  ['scripts/backend-check.mjs'],
]) {
  const result = spawnSync(process.execPath, args, { stdio: 'inherit', env });
  if (result.error) console.error(result.error);
  if (result.status !== 0) process.exit(result.status ?? 1);
}
console.log('V1 dev checks: OK');
