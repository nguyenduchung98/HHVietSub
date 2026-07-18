import { ChildProcessWithoutNullStreams, spawn } from 'node:child_process';
import { EventEmitter } from 'node:events';
import path from 'node:path';
import readline from 'node:readline';

type RpcMessage = { id?: string; result?: unknown; error?: { message: string }; event?: string; data?: unknown };

export class BackendManager {
  private process: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private events = new EventEmitter();
  private nextId = 1;
  private starting: Promise<void> | null = null;

  constructor(private readonly userData: string) {}

  async start() {
    if (this.process && this.process.exitCode === null && !this.process.killed) return;
    if (this.starting) return this.starting;
    this.starting = this.spawnBackend();
    try { await this.starting; } finally { this.starting = null; }
  }

  private async spawnBackend() {
    const python = process.env.DCC_PYTHON ?? 'C:\\Users\\Admin\\AppData\\Roaming\\uv\\python\\cpython-3.12.13-windows-x86_64-none\\python.exe';
    const worker = path.resolve(__dirname, '..', 'backend', 'worker', 'main.py');
    this.process = spawn(python, [worker, '--user-data', this.userData], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    });
    readline.createInterface({ input: this.process.stdout }).on('line', (line) => this.handleLine(line));
    this.process.stderr.on('data', (data) => this.events.emit('event', { event: 'backend.log', data: String(data) }));
    this.process.on('error', (error) => this.failPending(new Error(`Backend không khởi động được: ${error.message}`)));
    this.process.on('exit', (code) => {
      this.failPending(new Error(`Backend đã dừng (mã ${code ?? 'không xác định'}). Yêu cầu tiếp theo sẽ tự khởi động lại.`));
      this.process = null;
      this.events.emit('event', { event: 'backend.state', data: { online: false, code } });
    });
    await this.request('system.ping', {});
  }

  async request(method: string, params: unknown): Promise<unknown> {
    if (!this.process || this.process.exitCode !== null || this.process.killed) await this.start();
    if (!this.process || !this.process.stdin.writable) throw new Error('Backend chưa sẵn sàng');
    const id = String(this.nextId++);
    return new Promise((resolve, reject) => {
      const timeoutMs = method === 'studio.generate' || method === 'subtitle.translate.browser' || method.startsWith('srt.voice.') || method === 'capcut.project.create' ? 30 * 60_000 : 30_000;
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Backend không phản hồi đúng thời hạn (${method}).`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (value) => { clearTimeout(timeout); resolve(value); },
        reject: (error) => { clearTimeout(timeout); reject(error); },
      });
      this.process!.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n', (error) => {
        if (!error) return;
        const pending = this.pending.get(id);
        this.pending.delete(id);
        pending?.reject(new Error(`Không gửi được yêu cầu đến backend: ${error.message}`));
      });
    });
  }

  onEvent(handler: (event: RpcMessage) => void) { this.events.on('event', handler); }
  stop() { this.process?.kill(); this.process = null; }

  private failPending(error: Error) {
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
  }

  private handleLine(line: string) {
    try {
      const message: RpcMessage = JSON.parse(line);
      if (message.event) return this.events.emit('event', message);
      if (!message.id) return;
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      message.error ? pending.reject(new Error(message.error.message)) : pending.resolve(message.result);
    } catch (error) {
      this.events.emit('event', { event: 'backend.log', data: `Protocol error: ${String(error)}` });
    }
  }
}
