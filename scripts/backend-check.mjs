import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const candidates = [
  'C:\\Users\\Admin\\AppData\\Roaming\\uv\\python\\cpython-3.12.13-windows-x86_64-none\\python.exe',
  process.env.DCC_PYTHON,
  'python',
].filter(Boolean);

const python = candidates.find((item) => item === 'python' || existsSync(item));
if (!python) throw new Error('Không tìm thấy Python 3.12. Hãy đặt biến DCC_PYTHON.');
const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => key !== 'Path'));
const result = spawnSync(python, ['backend/worker/main.py', '--self-test'], { stdio: 'inherit', env });
if (result.error) console.error(result.error);
process.exit(result.status ?? 1);
