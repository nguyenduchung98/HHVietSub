import { spawn, ChildProcess } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import fs from 'node:fs';

type SubtitleInput = { id: number; text: string };
type TranslationOptions = { gemUrl: string; modelName?: string; batchSize?: number; workers?: number; glossary?: string; entries: SubtitleInput[] };
type CdpTarget = { id: string; type: string; url: string; webSocketDebuggerUrl: string };

const INPUT_SELECTORS = ["rich-textarea div[contenteditable='true']", "div.ProseMirror[contenteditable='true']", "textarea", "div[contenteditable='true']"];
const RESPONSE_SELECTORS = ["model-response", ".model-response-text", ".response-container", "message-content", "div[data-test-id='conversation-turn']", "div[data-response-container='true']"];

class CdpSession {
  private socket: WebSocket;
  private nextId = 1;
  private pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void }>();
  private ready: Promise<void>;
  private closed = false;

  constructor(url: string) {
    this.socket = new WebSocket(url);
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener('open', () => resolve());
      this.socket.addEventListener('error', () => reject(new Error('Không kết nối được Chrome DevTools')));
    });
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data));
      if (!message.id) return;
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      message.error ? pending.reject(new Error(message.error.message)) : pending.resolve(message.result);
    });
    this.socket.addEventListener('close', () => {
      this.closed = true;
      for (const pending of this.pending.values()) pending.reject(new Error('Kết nối Chrome đã đóng'));
      this.pending.clear();
    });
  }

  async send(method: string, params: Record<string, unknown> = {}) {
    await this.ready;
    if (this.closed || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Tab Gemini đã đóng. Tiến trình dịch đã dừng.');
    }
    const id = this.nextId++;
    return new Promise<any>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('Chrome không phản hồi lệnh dịch trong 15 giây.'));
      }, 15_000);
      const settleResolve = (value: any) => {
        clearTimeout(timer);
        resolve(value);
      };
      const settleReject = (error: Error) => {
        clearTimeout(timer);
        reject(error);
      };
      this.pending.set(id, { resolve: settleResolve, reject: settleReject });
      try {
        this.socket.send(JSON.stringify({ id, method, params }));
      } catch (error) {
        this.pending.delete(id);
        settleReject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  async evaluate(expression: string) {
    const result = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'Lỗi JavaScript trong tab Gemini');
    return result.result?.value;
  }

  close() { this.socket.close(); }
}

export class GeminiCdpManager {
  private readonly port = 9333;
  private chrome: ChildProcess | null = null;
  private cancelled = false;
  private paused = false;

  constructor(private readonly profilePath: string, private readonly notify: (event: unknown) => void) {}

  private chromePath() {
    const candidates = [
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
      path.join(process.env.LOCALAPPDATA || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ];
    const found = candidates.find((candidate) => fs.existsSync(candidate));
    if (!found) throw new Error('Không tìm thấy Google Chrome');
    return found;
  }

  private requestJson<T>(pathname: string, method = 'GET'): Promise<T> {
    return new Promise((resolve, reject) => {
      const request = http.request({ hostname: '127.0.0.1', port: this.port, path: pathname, method }, (response) => {
        let body = '';
        response.setEncoding('utf8'); response.on('data', (chunk) => body += chunk);
        response.on('end', () => { try { resolve(JSON.parse(body)); } catch { reject(new Error('Chrome CDP trả dữ liệu không hợp lệ')); } });
      });
      request.on('error', reject); request.end();
    });
  }

  private requestText(pathname: string, method = 'GET'): Promise<string> {
    return new Promise((resolve, reject) => {
      const request = http.request({ hostname: '127.0.0.1', port: this.port, path: pathname, method }, (response) => {
        let body = '';
        response.setEncoding('utf8');
        response.on('data', (chunk) => body += chunk);
        response.on('end', () => resolve(body));
      });
      request.on('error', reject);
      request.end();
    });
  }

  private async ensureChrome(initialUrl = 'https://gemini.google.com/') {
    try { await this.requestJson('/json/version'); return; } catch { /* launch below */ }
    fs.mkdirSync(this.profilePath, { recursive: true });
    this.chrome = spawn(this.chromePath(), [
      `--remote-debugging-port=${this.port}`, `--user-data-dir=${this.profilePath}`, '--profile-directory=Default',
      '--no-first-run', '--no-default-browser-check', initialUrl,
    ], { stdio: 'ignore', windowsHide: false });
    const deadline = Date.now() + 20_000;
    while (Date.now() < deadline) {
      try { await this.requestJson('/json/version'); return; } catch { await new Promise((resolve) => setTimeout(resolve, 350)); }
    }
    throw new Error('Chrome không mở được cổng điều khiển CDP');
  }

  async open(url: string) {
    await this.ensureChrome(url);
    const desiredHost = new URL(url).hostname;
    const targets = await this.requestJson<CdpTarget[]>('/json');
    const existing = targets.find((target) => {
      if (target.type !== 'page' || !target.webSocketDebuggerUrl) return false;
      try { return new URL(target.url).hostname === desiredHost; } catch { return false; }
    });
    if (existing) {
      const session = new CdpSession(existing.webSocketDebuggerUrl);
      try {
        if (existing.url !== url) await session.send('Page.navigate', { url });
        await session.send('Page.bringToFront');
      } finally {
        session.close();
      }
      return { opened: true, reused: true };
    }
    await this.createTarget(url);
    return { opened: true, reused: false };
  }
  async login() { return this.open('https://accounts.google.com/'); }
  cancel() { this.cancelled = true; this.paused = false; }
  setPaused(value: boolean) { this.paused = value; return { paused: value }; }

  private async createTarget(url: string): Promise<CdpTarget> {
    return this.requestJson<CdpTarget>(`/json/new?${encodeURIComponent(url)}`, 'PUT');
  }

  private async waitReady(session: CdpSession) {
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) {
      const ready = await session.evaluate(`document.readyState !== 'loading' && !!document.querySelector(${JSON.stringify(INPUT_SELECTORS.join(','))})`);
      if (ready) return;
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
    throw new Error('Gemini chưa sẵn sàng. Hãy kiểm tra đăng nhập Google.');
  }

  private buildPrompt(chunk: SubtitleInput[], glossary: string) {
    const rules = `Dịch từng block sang tiếng Việt. Giữ ánh xạ 1:1, không gộp hoặc tách block. Chỉ trả về: #1 bản dịch ; #2 bản dịch. Trả đủ, không thiếu không thừa.${glossary ? `\nThuật ngữ bắt buộc:\n${glossary}` : ''}`;
    return `${rules}\n\n${chunk.map((item) => `#${item.id} ${item.text.replace(/\s+/g, ' ').trim()}`).join(' ; ')}`;
  }

  private async submit(session: CdpSession, prompt: string) {
    const previous = await session.evaluate(`(() => { const a=[...document.querySelectorAll(${JSON.stringify(RESPONSE_SELECTORS.join(','))})].filter(e=>e.offsetParent); return a.at(-1)?.innerText?.trim()||'' })()`);
    const focused = await session.evaluate(`(() => { const sels=${JSON.stringify(INPUT_SELECTORS)}; const el=sels.map(s=>[...document.querySelectorAll(s)].find(x=>x.offsetParent)).find(Boolean); if(!el)return false; el.focus(); if(el.tagName==='TEXTAREA'){el.value='';el.dispatchEvent(new Event('input',{bubbles:true}))}else{document.execCommand('selectAll');document.execCommand('delete')} return true })()`);
    if (!focused) throw new Error('Không tìm thấy ô nhập của Gemini');
    await session.send('Input.insertText', { text: prompt });
    await new Promise((resolve) => setTimeout(resolve, 250));
    const sent = await session.evaluate(`(() => { const buttons=[...document.querySelectorAll('button,[role="button"]')].filter(e=>e.offsetParent); const b=buttons.find(e=>/send|submit|gửi/i.test((e.getAttribute('aria-label')||e.textContent||'')) && !e.disabled); if(b){b.click();return true} const el=document.activeElement; if(el){el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));return true} return false })()`);
    if (!sent) throw new Error('Không bấm được nút gửi Gemini');
    await new Promise((resolve) => setTimeout(resolve, 450));
    const draftRemains = await session.evaluate(`(() => { const sels=${JSON.stringify(INPUT_SELECTORS)}; const el=sels.map(s=>[...document.querySelectorAll(s)].find(x=>x.offsetParent)).find(Boolean); if(!el)return false; const value=('value' in el ? el.value : el.innerText)||''; return value.trim().length > 0 })()`);
    if (draftRemains) {
      await session.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
      await session.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
    }
    const deadline = Date.now() + 180_000; let last = ''; let stable = 0;
    while (Date.now() < deadline) {
      if (this.cancelled) throw new Error('Đã hủy dịch');
      while (this.paused && !this.cancelled) await new Promise((resolve) => setTimeout(resolve, 300));
      const state = await session.evaluate(`(() => { const a=[...document.querySelectorAll(${JSON.stringify(RESPONSE_SELECTORS.join(','))})].filter(e=>e.offsetParent); const text=a.at(-1)?.innerText?.trim()||''; const generating=[...document.querySelectorAll('button')].some(e=>e.offsetParent&&/stop|dừng/i.test(e.getAttribute('aria-label')||'')); return {text,generating} })()`);
      if (state.text && state.text !== previous && /#\s*\d+/.test(state.text)) {
        stable = state.text === last ? stable + 1 : 0; last = state.text;
        if ((!state.generating && stable >= 1) || stable >= 3) return state.text;
      }
      await new Promise((resolve) => setTimeout(resolve, 650));
    }
    throw new Error('Hết thời gian chờ Gemini trả kết quả');
  }

  private parse(text: string, expected: number[]) {
    const result = new Map<number, string>();
    const pattern = /#\s*(\d+)\s*[:.)-]?\s*(.*?)(?=(?:\s*(?:;|\n)\s*#\s*\d+)|$)/gs;
    for (const match of text.replace(/```\w*/g, '').replace(/```/g, '').matchAll(pattern)) result.set(Number(match[1]), match[2].trim().replace(/;$/, '').trim());
    return { result, missing: expected.filter((id) => !result.has(id)) };
  }

  async translate(options: TranslationOptions) {
    if (!options.entries?.length) throw new Error('Không có phụ đề để dịch');
    if (!options.gemUrl?.startsWith('https://gemini.google.com/')) throw new Error('Link Gem không hợp lệ');
    this.cancelled = false; this.paused = false;
    await this.ensureChrome(options.gemUrl);
    const batchSize = Math.max(1, Math.min(300, options.batchSize || 200));
    const workers = Math.max(1, Math.min(5, options.workers || 1));
    const chunks = Array.from({ length: Math.ceil(options.entries.length / batchSize) }, (_, i) => options.entries.slice(i * batchSize, i * batchSize + batchSize));
    const openTargets = await this.requestJson<CdpTarget[]>('/json');
    const geminiTargets = openTargets.filter((target) => {
      if (target.type !== 'page' || !target.webSocketDebuggerUrl) return false;
      try { return new URL(target.url).hostname === 'gemini.google.com'; } catch { return false; }
    });
    const reusable = geminiTargets.slice(0, workers);
    const surplus = geminiTargets.slice(workers);
    await Promise.all(surplus.map((target) => this.requestText(`/json/close/${target.id}`)));
    const missingWorkers = workers - reusable.length;
    const created = missingWorkers > 0
      ? await Promise.all(Array.from({ length: missingWorkers }, () => this.createTarget(options.gemUrl)))
      : [];
    const targets = [...reusable, ...created];
    const sessions = targets.map((target) => new CdpSession(target.webSocketDebuggerUrl));
    await Promise.all(sessions.map((session, index) =>
      reusable[index] && reusable[index].url !== options.gemUrl
        ? session.send('Page.navigate', { url: options.gemUrl })
        : Promise.resolve()
    ));
    await Promise.all(sessions.map((session) => this.waitReady(session)));
    const results = new Map<number, string>(); let cursor = 0; let done = 0;
    const runWorker = async (session: CdpSession, worker: number) => {
      while (!this.cancelled) {
        const index = cursor++; if (index >= chunks.length) return;
        let pending = chunks[index];
        for (let attempt = 1; attempt <= 3 && pending.length; attempt++) {
          this.notify({ event: 'translation.progress', data: { done, total: chunks.length, chunk: index + 1, worker: worker + 1, attempt } });
          const raw = await this.submit(session, this.buildPrompt(pending, options.glossary || ''));
          const parsed = this.parse(raw, pending.map((item) => item.id));
          for (const [id, value] of parsed.result) results.set(id, value);
          pending = pending.filter((item) => parsed.missing.includes(item.id));
        }
        if (pending.length) throw new Error(`Gemini thiếu ${pending.length} câu ở chunk ${index + 1}`);
        done++; this.notify({ event: 'translation.progress', data: { done, total: chunks.length, chunk: index + 1, worker: worker + 1 } });
      }
    };
    let completed = false;
    try {
      await Promise.all(sessions.map(runWorker));
      completed = true;
    } finally {
      sessions.forEach((session) => session.close());
    }
    if (completed) {
      await Promise.allSettled(targets.map((target) => this.requestText(`/json/close/${target.id}`)));
    }
    return { results: [...results].sort((a,b)=>a[0]-b[0]).map(([id, translated]) => ({ id, translated })), chunks: chunks.length };
  }
}
