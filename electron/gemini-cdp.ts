import { spawn, ChildProcess } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import fs from 'node:fs';

type SubtitleInput = { id: number; text: string };
type TranslationOptions = { gemUrl: string; modelName?: string; batchSize?: number; workers?: number; glossary?: string; characterBible?: string; entries: SubtitleInput[] };
type CdpTarget = { id: string; type: string; url: string; webSocketDebuggerUrl: string };

const INPUT_SELECTORS = ["rich-textarea div[contenteditable='true']", "div.ProseMirror[contenteditable='true']", "textarea", "div[contenteditable='true']"];
// Only read assistant turns. Generic conversation/message selectors also match
// the user's prompt, which made source #id lines look like completed translations.
const RESPONSE_SELECTORS = ["model-response"];

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
  private submitLock: Promise<void> = Promise.resolve();

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

  private async acquireSubmitLock() {
    let release!: () => void;
    const previous = this.submitLock;
    this.submitLock = new Promise<void>((resolve) => { release = resolve; });
    await previous;
    return release;
  }

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

  private async clickPosition(session: CdpSession, position: { x: number; y: number }) {
    await session.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: position.x, y: position.y, button: 'left', clickCount: 1 });
    await session.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: position.x, y: position.y, button: 'left', clickCount: 1 });
  }

  private modelMatchesHeader(header: unknown, desired: string) {
    const compact = String(header).replace(/\s+/g, '').toLowerCase();
    const exact = desired.replace(/\s+/g, '').toLowerCase();
    if (compact.includes(exact)) return true;
    if (desired === '3.5 Flash-Lite') return compact.includes('geminiflash-lite');
    if (desired === '3.6 Flash') return compact.includes('geminiflash') && !compact.includes('flash-lite');
    if (desired === '3.1 Pro') return compact.includes('geminipro');
    if (desired === 'Tư duy mở rộng') return compact.includes('tưduymởrộng') || compact.includes('thinking');
    return false;
  }

  private async selectModel(session: CdpSession, requested = '') {
    const aliases: Record<string, string> = {
      '3.5 Flash': '3.6 Flash',
      '3.5 Flash-Lite': '3.5 Flash-Lite',
      '3.1 Flash-Lite': '3.5 Flash-Lite',
      '3.6 Flash': '3.6 Flash',
      '3.1 Pro': '3.1 Pro',
      'Tư duy mở rộng': 'Tư duy mở rộng',
    };
    const desired = aliases[requested] || requested || '3.5 Flash-Lite';
    const current = await session.evaluate(`(() => {
      const pattern=/Gemini\\s*(?:Flash(?:-Lite)?|Pro|Thinking)|3\\.[0-9]+\\s*(?:Flash(?:-Lite)?|Pro)|Tư duy mở rộng/i;
      const nodes=[...document.querySelectorAll('button,[role="button"]')].filter(e=>e.offsetParent&&e.getBoundingClientRect().top<180);
      return nodes.map(e=>(e.textContent||'').replace(/\\s+/g,' ').trim()).find(t=>pattern.test(t))||'';
    })()`);
    if (this.modelMatchesHeader(current, desired)) {
      this.notify({ event: 'translation.model', data: { model: desired, state: 'ready' } });
      return;
    }
    const trigger = await session.evaluate(`(() => {
      const pattern=/Gemini\\s*(?:Flash(?:-Lite)?|Pro|Thinking)|3\\.[0-9]+\\s*(?:Flash(?:-Lite)?|Pro)|Tư duy mở rộng/i;
      const nodes=[...document.querySelectorAll('button,[role="button"]')].filter(e=>e.offsetParent&&e.getBoundingClientRect().top<180);
      const el=nodes.find(e=>pattern.test((e.textContent||'').replace(/\\s+/g,' ').trim()));
      if(!el)return null;const r=el.getBoundingClientRect();return{x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};
    })()`);
    if (!trigger) throw new Error('Không tìm thấy nút chọn model trên Gemini');
    await this.clickPosition(session, trigger);
    await new Promise((resolve) => setTimeout(resolve, 500));
    const option = await session.evaluate(`((wanted) => {
      const nodes=[...document.querySelectorAll('button,[role="button"],[role="menuitem"],[role="option"]')].filter(e=>e.offsetParent);
      const matches=nodes.filter(e=>(e.textContent||'').replace(/\\s+/g,' ').trim().includes(wanted));
      const el=matches.sort((a,b)=>(a.textContent||'').length-(b.textContent||'').length)[0];
      if(!el)return null;const r=el.getBoundingClientRect();return{x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};
    })(${JSON.stringify(desired)})`);
    if (!option) throw new Error(`Model “${desired}” không có trong menu Gemini hiện tại`);
    await this.clickPosition(session, option);
    const verifyDeadline = Date.now() + 6_000;
    let selected = false;
    while (Date.now() < verifyDeadline) {
      const header = await session.evaluate(`(() => {
        const el=[...document.querySelectorAll('button[aria-label],button,[role="button"]')].find(e=>e.offsetParent&&e.getBoundingClientRect().top<180&&/Gemini\\s*(?:Flash(?:-Lite)?|Pro|Thinking)|3\\.[0-9]+\\s*(?:Flash(?:-Lite)?|Pro)|Tư duy mở rộng/i.test(((e.getAttribute('aria-label')||'')+' '+(e.textContent||''))));
        return el ? ((el.getAttribute('aria-label')||'')+' '+(el.textContent||'')).replace(/\\s+/g,' ').trim() : '';
      })()`);
      if (this.modelMatchesHeader(header, desired)) {
        selected = true; break;
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    if (!selected) throw new Error(`Gemini không chuyển sang model “${desired}” sau khi click`);
    this.notify({ event: 'translation.model', data: { model: desired, state: 'ready' } });
  }

  private buildPrompt(chunk: SubtitleInput[], glossary: string) {
    const rules = `Dịch từng block sang tiếng Việt. Giữ ánh xạ 1:1, không gộp hoặc tách block. Chỉ trả về: #1 bản dịch ; #2 bản dịch. Trả đủ, không thiếu không thừa.${glossary ? `\nThuật ngữ bắt buộc:\n${glossary}` : ''}`;
    return `${rules}\n\n${chunk.map((item) => `#${item.id} ${item.text.replace(/\s+/g, ' ').trim()}`).join(' ; ')}`;
  }

  private async submit(session: CdpSession, prompt: string, requireSubtitleIds = true) {
    const releaseSubmitLock = await this.acquireSubmitLock();
    let previous = '';
    try {
      // Trusted mouse input is ignored by background Chrome tabs. Bring each
      // worker forward only for its short submit phase; generation then
      // continues concurrently in the background.
      await session.send('Page.bringToFront');
    previous = await session.evaluate(`(() => { const a=[...document.querySelectorAll(${JSON.stringify(RESPONSE_SELECTORS.join(','))})].filter(e=>e.offsetParent); return a.at(-1)?.innerText?.trim()||'' })()`);
    const setSuccess = await session.evaluate(`((p) => {
      const sels=${JSON.stringify(INPUT_SELECTORS)};
      const el=sels.map(s=>[...document.querySelectorAll(s)].find(x=>x.offsetParent)).find(Boolean);
      if(!el) return false;
      el.focus();
      if(el.tagName==='TEXTAREA'){
        el.value=p;
        el.dispatchEvent(new Event('input',{bubbles:true}));
        el.dispatchEvent(new Event('change',{bubbles:true}));
      } else {
        el.innerText = p;
        el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText', data: p }));
        el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: p }));
        el.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
      }
      return true;
    })(${JSON.stringify(prompt)})`);

    if (!setSuccess) throw new Error('Không tìm thấy ô nhập của Gemini');
    await new Promise((resolve) => setTimeout(resolve, 250));

    // Fallback: If innerText wasn't filled, try Input.insertText
    const isFilled = await session.evaluate(`(() => {
      const sels=${JSON.stringify(INPUT_SELECTORS)};
      const el=sels.map(s=>[...document.querySelectorAll(s)].find(x=>x.offsetParent)).find(Boolean);
      if(!el) return false;
      const text = ('value' in el ? el.value : el.innerText) || '';
      return text.trim().length > 0;
    })()`);

    if (!isFilled) {
      await session.send('Input.insertText', { text: prompt });
      await new Promise((resolve) => setTimeout(resolve, 250));
      await session.evaluate(`(() => {
        const sels=${JSON.stringify(INPUT_SELECTORS)};
        const el=sels.map(s=>[...document.querySelectorAll(s)].find(x=>x.offsetParent)).find(Boolean);
        if(el) {
          el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText' }));
          el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText' }));
          el.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
        }
      })()`);
    }

    // Wait until Gemini has changed back from the previous response to a real,
    // enabled send button. Confirm that the composer consumed the draft.
    let submitted = false;
    const submitDeadline = Date.now() + 20_000;
    while (!submitted && Date.now() < submitDeadline) {
      if (this.cancelled) throw new Error('Đã hủy dịch');
      const composer = await session.evaluate(`(() => {
        const sels=${JSON.stringify(INPUT_SELECTORS)};
        const el=sels.map(s=>[...document.querySelectorAll(s)].find(x=>x.offsetParent)).find(Boolean);
        const draft=el ? ((('value' in el ? el.value : el.innerText) || '').trim()) : '';
        const selectors=['button.send-button','button.send-button-v2','.send-button-container button','button[data-test-id*="send" i]','button[aria-label*="send" i]','button[aria-label*="gửi" i]','button[aria-label*="submit" i]'];
        let button=selectors.map(s=>[...document.querySelectorAll(s)].find(x=>x.offsetParent&&!x.disabled)).find(Boolean);
        if(!button) button=[...document.querySelectorAll('button,[role="button"]')].find(x=>x.offsetParent&&!x.disabled&&/send|submit|gửi/i.test(x.getAttribute('aria-label')||x.textContent||''));
        if(!button) return {draft,position:null};
        const rect=button.getBoundingClientRect();
        return {draft,position:{x:Math.round(rect.left+rect.width/2),y:Math.round(rect.top+rect.height/2)}};
      })()`);
      const position = composer?.position;
      if (!position || position.x <= 0 || position.y <= 0) {
        await new Promise((resolve) => setTimeout(resolve, 300));
        continue;
      }
      await session.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: position.x, y: position.y, button: 'left', clickCount: 1 });
      await session.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: position.x, y: position.y, button: 'left', clickCount: 1 });
      await new Promise((resolve) => setTimeout(resolve, 650));
      submitted = await session.evaluate(`(() => {
        const sels=${JSON.stringify(INPUT_SELECTORS)};
        const el=sels.map(s=>[...document.querySelectorAll(s)].find(x=>x.offsetParent)).find(Boolean);
        const draft=el ? ((('value' in el ? el.value : el.innerText) || '').trim()) : '';
        const responses=[...document.querySelectorAll(${JSON.stringify(RESPONSE_SELECTORS.join(','))})].filter(e=>e.offsetParent);
        const latest=responses.at(-1)?.innerText?.trim()||'';
        const generating=[...document.querySelectorAll('button')].some(e=>e.offsetParent&&/stop|dừng/i.test((e.getAttribute('aria-label')||e.textContent||'')));
        return draft.length===0 || latest!==${JSON.stringify(previous)} || generating;
      })()`);
    }
    if (!submitted) throw new Error('Gemini đã nhận nội dung nhưng nút Gửi chưa sẵn sàng sau 20 giây');
    } finally {
      releaseSubmitLock();
    }

    const deadline = Date.now() + 180_000; let last = ''; let stable = 0;
    while (Date.now() < deadline) {
      if (this.cancelled) throw new Error('Đã hủy dịch');
      while (this.paused && !this.cancelled) await new Promise((resolve) => setTimeout(resolve, 300));
      const state = await session.evaluate(`(() => { const a=[...document.querySelectorAll(${JSON.stringify(RESPONSE_SELECTORS.join(','))})].filter(e=>e.offsetParent); const text=a.at(-1)?.innerText?.trim()||''; const generating=[...document.querySelectorAll('button')].some(e=>e.offsetParent&&/stop|dừng/i.test((e.getAttribute('aria-label')||e.textContent||''))); return {text,generating} })()`);
      if (state.text && state.text !== previous && (!requireSubtitleIds || /#\s*\d+/.test(state.text))) {
        stable = state.text === last ? stable + 1 : 0; last = state.text;
        if (!state.generating && stable >= 2) return state.text;
      }
      await new Promise((resolve) => setTimeout(resolve, 650));
    }
    throw new Error('Hết thời gian chờ Gemini trả kết quả');
  }

  private parse(text: string, expected: number[]) {
    const result = new Map<number, string>();
    const allowed = new Set(expected);
    const cleanedText = text
      .replace(/\*\*/g, '')
      .replace(/```\w*/g, '')
      .replace(/```/g, '');
    const pattern = /#\s*(\d+)\s*[:.)-]?\s*(.*?)(?=(?:\s*(?:;|\n)\s*#\s*\d+)|$)/gs;
    for (const match of cleanedText.matchAll(pattern)) {
      const id = Number(match[1]);
      const translated = match[2].trim().replace(/;$/, '').trim();
      if (allowed.has(id) && translated) result.set(id, translated);
    }
    return { result, missing: expected.filter((id) => !result.has(id)) };
  }

  async translate(options: TranslationOptions) {
    if (!options.entries?.length) throw new Error('Không có phụ đề để dịch');
    if (!options.characterBible?.trim()) throw new Error('Chưa chọn hoặc Character Bible đang trống');
    if (!options.gemUrl?.startsWith('https://gemini.google.com/')) throw new Error('Link Gem không hợp lệ');
    this.cancelled = false; this.paused = false;
    await this.ensureChrome(options.gemUrl);
    const batchSize = Math.max(1, Math.min(300, options.batchSize || 200));
    // Gemini UI automation is most reliable with one foreground tab. Keep
    // chunks sequential so prompts and responses cannot cross between tabs.
    const workers = 1;
    const chunks = Array.from({ length: Math.ceil(options.entries.length / batchSize) }, (_, i) => options.entries.slice(i * batchSize, i * batchSize + batchSize));
    const openTargets = await this.requestJson<CdpTarget[]>('/json');
    const geminiTargets = openTargets.filter((target) => {
      if (target.type !== 'page' || !target.webSocketDebuggerUrl) return false;
      try { return new URL(target.url).hostname === 'gemini.google.com'; } catch { return false; }
    });
    const reusable = geminiTargets.slice(0, workers);
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
    let completed = false;
    try {
    await this.selectModel(sessions[0], options.modelName);
    this.notify({ event: 'translation.started', data: { total: chunks.length, entries: options.entries.length, workers } });
    this.notify({ event: 'translation.bible', data: { state: 'loading', characters: options.characterBible.length } });
    const biblePrompt = [
      'Hãy đọc và ghi nhớ toàn bộ Character Bible dưới đây để dùng nhất quán cho tất cả chunk phụ đề tiếp theo.',
      'Không dịch phụ đề ở bước này. Sau khi nạp xong, chỉ trả lời chính xác câu:',
      'Đã nạp Character Bible — sẵn sàng nhận chunk để dịch.',
      '',
      '--- CHARACTER BIBLE ---',
      options.characterBible.trim(),
      '--- HẾT CHARACTER BIBLE ---',
    ].join('\n');
    const bibleResponse = await this.submit(sessions[0], biblePrompt, false);
    const normalizedBibleResponse = bibleResponse.replace(/[–—]/g, '—').replace(/\s+/g, ' ').trim();
    const expectedBibleAck = 'Đã nạp Character Bible — sẵn sàng nhận chunk để dịch.';
    if (!normalizedBibleResponse.includes(expectedBibleAck)) {
      throw new Error(`Gem chưa xác nhận Character Bible đúng yêu cầu. Phản hồi: ${bibleResponse.slice(0, 500)}`);
    }
    this.notify({ event: 'translation.bible', data: { state: 'ready', message: expectedBibleAck } });
    const runWorker = async (session: CdpSession, worker: number) => {
      while (!this.cancelled) {
        const index = cursor++; if (index >= chunks.length) return;
        let pending = chunks[index];
        for (let attempt = 1; attempt <= 3 && pending.length; attempt++) {
          this.notify({ event: 'translation.progress', data: { done, total: chunks.length, chunk: index + 1, worker: worker + 1, attempt } });
          try {
            const raw = await this.submit(session, this.buildPrompt(pending, options.glossary || ''));
            const parsed = this.parse(raw, pending.map((item) => item.id));
            for (const [id, value] of parsed.result) results.set(id, value);
            if (parsed.result.size) {
              this.notify({ event: 'translation.result', data: { chunk: index + 1, worker: worker + 1,
                results: [...parsed.result].map(([id, translated]) => ({ id, translated })) } });
            }
            pending = pending.filter((item) => parsed.missing.includes(item.id));
          } catch (error) {
            if (this.cancelled || attempt === 3) throw error;
            this.notify({ event: 'translation.retry', data: { chunk: index + 1, worker: worker + 1,
              attempt: attempt + 1, message: error instanceof Error ? error.message : String(error) } });
          }
        }
        if (pending.length) throw new Error(`Gemini thiếu ${pending.length} câu ở chunk ${index + 1}`);
        done++; this.notify({ event: 'translation.progress', data: { done, total: chunks.length, chunk: index + 1, worker: worker + 1 } });
      }
    };
      await Promise.all(sessions.map(runWorker));
      completed = true;
    } finally {
      sessions.forEach((session) => session.close());
    }
    // The translation workflow owns its Gem tab. Close it after a successful
    // run even when Chrome supplied a reusable tab.
    if (completed) await Promise.allSettled(targets.map((target) => this.requestText(`/json/close/${target.id}`)));
    return { results: [...results].sort((a,b)=>a[0]-b[0]).map(([id, translated]) => ({ id, translated })), chunks: chunks.length };
  }
}
