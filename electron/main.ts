import { app, BrowserWindow, dialog, ipcMain, Menu, Notification, shell } from 'electron';
import type { IpcMainInvokeEvent, OpenDialogOptions } from 'electron';
import path from 'node:path';
import fs from 'node:fs/promises';
import { existsSync, mkdirSync, statSync } from 'node:fs';
import { BackendManager } from './backend-manager';
import { AppSecrets, SecretStore } from './secret-store';

let window: BrowserWindow | null = null;
let backend: BackendManager | null = null;

const grantedFiles = new Set<string>();
const grantedDirectories = new Set<string>();
const normalizePath = (value: string) => path.resolve(value).toLowerCase();

const assertTrustedSender = (event: IpcMainInvokeEvent) => {
  if (!window || window.isDestroyed() || event.sender.id !== window.webContents.id || event.senderFrame !== window.webContents.mainFrame) {
    throw new Error('Nguồn IPC không hợp lệ');
  }
};

const grantPath = (value: string) => {
  if (!path.isAbsolute(value) || !existsSync(value)) return;
  const normalized = normalizePath(value);
  try {
    if (statSync(value).isDirectory()) grantedDirectories.add(normalized);
    else grantedFiles.add(normalized);
  } catch { /* path disappeared before it could be granted */ }
};

const PATH_RESULT_KEYS = new Set([
  'path', 'file', 'outputDir', 'manifestPath', 'projectPath', 'referenceAudio',
  'localPath', 'profilePath', 'audioPath', 'videoPath', 'srtPath', 'voiceDir',
]);

const RENDERER_RPC_METHODS = new Set([
  'system.ping',
  'project.list',
  'settings.tts.get', 'settings.tts.save', 'settings.tts.test',
  'tts.voices.list',
  'tts.voice.preview',
  'subtitle.parse',
  'srt.voice.generate', 'srt.voice.regenerate', 'srt.voice.control', 'srt.voice.latest', 'srt.voice.list', 'srt.voice.get',
  'capcut.project.validate_existing', 'capcut.project.sync', 'capcut.open',
  'ffmpeg.sync.validate', 'ffmpeg.sync.create',
]);

const grantResultPaths = (value: unknown) => {
  if (Array.isArray(value)) {
    value.forEach(grantResultPaths);
  } else if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      if (PATH_RESULT_KEYS.has(key) && typeof child === 'string') grantPath(child);
      else if (child && typeof child === 'object') grantResultPaths(child);
    }
  }
};

const assertGrantedPath = (value: string) => {
  const normalized = normalizePath(value);
  if (grantedFiles.has(normalized)) return path.resolve(value);
  for (const directory of grantedDirectories) {
    const relative = path.relative(directory, normalized);
    if (!relative.startsWith('..') && !path.isAbsolute(relative)) return path.resolve(value);
  }
  throw new Error('Đường dẫn chưa được người dùng hoặc backend cấp quyền');
};

const sanitizeFileDialogOptions = (value: unknown): Pick<OpenDialogOptions, 'filters' | 'title'> => {
  if (!value || typeof value !== 'object') return {};
  const raw = value as { title?: unknown; filters?: unknown };
  const title = typeof raw.title === 'string' ? raw.title.slice(0, 100) : undefined;
  const filters = Array.isArray(raw.filters) ? raw.filters.slice(0, 10).flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const entry = item as { name?: unknown; extensions?: unknown };
    if (typeof entry.name !== 'string' || !Array.isArray(entry.extensions)) return [];
    const extensions = entry.extensions
      .filter((extension): extension is string => typeof extension === 'string' && /^[a-z0-9]{1,10}$/i.test(extension))
      .slice(0, 20);
    return extensions.length ? [{ name: entry.name.slice(0, 50), extensions }] : [];
  }) : undefined;
  return { ...(title ? { title } : {}), ...(filters?.length ? { filters } : {}) };
};

// Chromium caches are machine-local and should not live beside persistent app
// data in Roaming. A stale/locked cache there can leave the renderer blank.
const liteDataRoot = path.join(process.env.LOCALAPPDATA || app.getPath('appData'), 'HHVietSub Lite');
const sessionDataPath = path.join(liteDataRoot, 'SessionData');
mkdirSync(sessionDataPath, { recursive: true });
app.setPath('userData', liteDataRoot);
app.setPath('sessionData', sessionDataPath);
app.commandLine.appendSwitch('disk-cache-dir', path.join(sessionDataPath, 'Cache'));

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) app.quit();

const createWindow = async () => {
  window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    backgroundColor: '#f5f7ff',
    title: 'HHVietSub Lite',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      defaultEncoding: 'UTF-8',
    },
  });

  window.on('closed', () => {
    window = null;
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const parsed = new URL(url);
      if (parsed.protocol === 'https:') void shell.openExternal(parsed.toString());
    } catch { /* deny malformed URLs */ }
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', (event, url) => {
    const allowed = app.isPackaged ? url.startsWith('file:') : url.startsWith('http://localhost:5173');
    if (!allowed) event.preventDefault();
  });
  window.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));

  const distIndex = path.join(app.getAppPath(), 'dist', 'index.html');
  if (app.isPackaged) {
    await window.loadFile(distIndex);
  } else {
    try {
      await window.loadURL('http://localhost:5173');
    } catch {
      await window.loadFile(distIndex);
    }
  }
};

app.setName('HHVietSub Lite');

app.whenReady().then(async () => {
  if (!hasSingleInstanceLock) return;
  Menu.setApplicationMenu(null);
  const sendEvent = (event: unknown) => {
    if (window && !window.isDestroyed()) {
      grantResultPaths(event);
      window.webContents.send('backend:event', event);
    }
  };

  const userDataPath = app.getPath('userData');
  backend = new BackendManager(userDataPath);
  backend.onEvent(sendEvent);
  await backend.start();

  const secretStore = new SecretStore(userDataPath);
  await backend.request('settings.secrets.set', await secretStore.getAll());

  ipcMain.handle('backend:request', async (event, method: string, params: unknown) => {
    assertTrustedSender(event);
    if (typeof method !== 'string' || !RENDERER_RPC_METHODS.has(method)) throw new Error('RPC không được phép gọi từ giao diện');
    const fields = params && typeof params === 'object' ? params as Record<string, unknown> : {};
    const secrets: Partial<AppSecrets> = {};
    if (method === 'settings.tts.save' || method === 'settings.tts.test') {
      if (String(fields.ai33Key || '').trim()) secrets.ai33Key = String(fields.ai33Key).trim();
      if (String(fields.aimaxKey || '').trim()) secrets.aimaxKey = String(fields.aimaxKey).trim();
      if (fields.provider === 'ai33' && String(fields.key || '').trim()) secrets.ai33Key = String(fields.key).trim();
      if (fields.provider === 'aimax' && String(fields.key || '').trim()) secrets.aimaxKey = String(fields.key).trim();
    }
    if (Object.keys(secrets).length) {
      await secretStore.merge(secrets);
      await backend?.request('settings.secrets.set', await secretStore.getAll());
    }
    const result = await backend?.request(method, fields);
    grantResultPaths(result);
    const isSrtGeneration = method === 'srt.voice.generate' || method === 'srt.voice.regenerate';
    const summary = result as { completed?: number; failed?: number; total?: number; state?: string } | undefined;
    if (isSrtGeneration && summary && Number(summary.total) > 0 && summary.state !== 'cancelled' && Notification.isSupported()) {
      new Notification({
        title: 'HHVietSub · Tạo giọng hoàn tất',
        body: `${summary.completed ?? 0}/${summary.total ?? 0} câu thành công${summary.failed ? ` · ${summary.failed} câu lỗi` : ''}.`,
      }).show();
      if (window && !window.isDestroyed()) {
        window.flashFrame(true);
        setTimeout(() => { if (window && !window.isDestroyed()) window.flashFrame(false); }, 3000);
      }
    }
    if ((method === 'capcut.project.create' || method === 'capcut.project.sync') && result && Notification.isSupported()) {
      const project = result as { projectName?: string };
      new Notification({ title: 'HHVietSub · Dự án CapCut hoàn tất', body: `Đã tạo và đồng bộ ${project.projectName || 'project mới'}.` }).show();
      if (window && !window.isDestroyed()) {
        window.flashFrame(true);
        setTimeout(() => { if (window && !window.isDestroyed()) window.flashFrame(false); }, 3000);
      }
    }
    return result;
  });
  ipcMain.handle('dialog:file', async (event, options: unknown) => {
    assertTrustedSender(event);
    const result = await dialog.showOpenDialog(window!, { properties: ['openFile'], ...sanitizeFileDialogOptions(options) });
    if (!result.canceled && result.filePaths[0]) grantPath(result.filePaths[0]);
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('folder:srt-files', async (event, requestedFolder: string) => {
    assertTrustedSender(event);
    const folder = assertGrantedPath(requestedFolder);
    const metadata = await fs.stat(folder);
    if (!metadata.isDirectory()) throw new Error('Đường dẫn đã chọn không phải thư mục');
    const entries = await fs.readdir(folder, { withFileTypes: true });
    const files = entries
      .filter((entry) => entry.isFile() && path.extname(entry.name).toLowerCase() === '.srt')
      .map((entry) => path.join(folder, entry.name))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true, sensitivity: 'base' }));
    files.forEach(grantPath);
    return { folder, files };
  });
  ipcMain.handle('file:text-data', async (event, filePath: string) => {
    assertTrustedSender(event);
    const safePath = assertGrantedPath(filePath);
    if (!['.txt', '.md', '.json', '.csv'].includes(path.extname(safePath).toLowerCase())) {
      throw new Error('Character Bible phải là tệp TXT, MD, JSON hoặc CSV');
    }
    const stats = await fs.stat(safePath);
    if (!stats.isFile() || stats.size > 5 * 1024 * 1024) throw new Error('Character Bible vượt quá giới hạn 5 MB');
    return fs.readFile(safePath, 'utf8');
  });
  ipcMain.handle('dialog:folder', async (event) => {
    assertTrustedSender(event);
    const result = await dialog.showOpenDialog(window!, { properties: ['openDirectory'] });
    if (!result.canceled && result.filePaths[0]) grantPath(result.filePaths[0]);
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('file:audio-data', async (event, filePath: string) => {
    assertTrustedSender(event);
    const source = assertGrantedPath(filePath);
    if (path.extname(source).toLowerCase() !== '.wav') throw new Error('Chỉ cho phép đọc file WAV');
    const metadata = await fs.stat(source);
    if (metadata.size > 200 * 1024 * 1024) throw new Error('File audio vượt quá giới hạn 200 MB');
    const data = await fs.readFile(source);
    return `data:audio/wav;base64,${data.toString('base64')}`;
  });
  ipcMain.handle('file:save-audio', async (event, filePath: string) => {
    assertTrustedSender(event);
    const source = assertGrantedPath(filePath);
    const result = await dialog.showSaveDialog(window!, { defaultPath: path.basename(source), filters: [{ name: 'WAV Audio', extensions: ['wav'] }] });
    if (result.canceled || !result.filePath) return null;
    await fs.copyFile(source, result.filePath);
    const srtSource = source.replace(/\.wav$/i, '.srt');
    try { await fs.copyFile(srtSource, result.filePath.replace(/\.wav$/i, '.srt')); } catch { /* optional companion */ }
    grantPath(result.filePath);
    return result.filePath;
  });
  ipcMain.handle('file:show-in-folder', (event, filePath: string) => {
    assertTrustedSender(event);
    return shell.showItemInFolder(assertGrantedPath(filePath));
  });
  ipcMain.handle('external:open', (event, url: string) => {
    assertTrustedSender(event);
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') throw new Error('Chỉ cho phép mở liên kết HTTPS');
    return shell.openExternal(parsed.toString());
  });
  await createWindow();
});

app.on('second-instance', () => {
  if (!window) return;
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
});

app.on('window-all-closed', () => {
  backend?.stop();
  if (process.platform !== 'darwin') app.quit();
});
