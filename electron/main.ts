import { app, BrowserWindow, dialog, ipcMain, Notification, shell } from 'electron';
import path from 'node:path';
import fs from 'node:fs/promises';
import { BackendManager } from './backend-manager';
import { GeminiCdpManager } from './gemini-cdp';

let window: BrowserWindow | null = null;
let backend: BackendManager | null = null;
let gemini: GeminiCdpManager | null = null;

const createWindow = async () => {
  window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    backgroundColor: '#f5f7ff',
    title: 'Dich CapCut Studio',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  await window.loadURL('http://localhost:5173');
};

app.whenReady().then(async () => {
  backend = new BackendManager(app.getPath('userData'));
  gemini = new GeminiCdpManager('D:\\Dịch-Đồng Bộ\\chrome_profile', (event) => window?.webContents.send('backend:event', event));
  backend.onEvent((event) => window?.webContents.send('backend:event', event));
  await backend.start();

  ipcMain.handle('backend:request', async (_event, method: string, params: unknown) => {
    const result = await backend?.request(method, params ?? {});
    if (method.startsWith('srt.voice.') && result && Notification.isSupported()) {
      const summary = result as { completed?: number; failed?: number; total?: number };
      new Notification({
        title: 'HHVietSub · Tạo giọng hoàn tất',
        body: `${summary.completed ?? 0}/${summary.total ?? 0} câu thành công${summary.failed ? ` · ${summary.failed} câu lỗi` : ''}.`,
      }).show();
      window?.flashFrame(true);
      setTimeout(() => window?.flashFrame(false), 3000);
    }
    if (method === 'capcut.project.create' && result && Notification.isSupported()) {
      const project = result as { projectName?: string };
      new Notification({ title: 'HHVietSub · Dự án CapCut hoàn tất', body: `Đã tạo và đồng bộ ${project.projectName || 'project mới'}.` }).show();
      window?.flashFrame(true);
      setTimeout(() => window?.flashFrame(false), 3000);
    }
    return result;
  });
  ipcMain.handle('gemini:translate', async (_event, params) => {
    const result = await gemini?.translate(params);
    if (result && Notification.isSupported()) {
      new Notification({
        title: 'HHVietSub',
        body: `Đã dịch xong ${result.results.length} câu trong ${result.chunks} chunk.`,
      }).show();
    }
    window?.show();
    window?.flashFrame(true);
    setTimeout(() => window?.flashFrame(false), 3000);
    return result;
  });
  ipcMain.handle('gemini:open', (_event, url: string) => gemini?.open(url));
  ipcMain.handle('gemini:login', () => gemini?.login());
  ipcMain.handle('gemini:cancel', () => gemini?.cancel());
  ipcMain.handle('gemini:pause', (_event, paused: boolean) => gemini?.setPaused(paused));
  ipcMain.handle('dialog:file', async (_event, options) => {
    const result = await dialog.showOpenDialog(window!, { properties: ['openFile'], ...options });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('dialog:folder', async () => {
    const result = await dialog.showOpenDialog(window!, { properties: ['openDirectory'] });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('file:audio-data', async (_event, filePath: string) => {
    if (path.extname(filePath).toLowerCase() !== '.wav') throw new Error('Chỉ cho phép đọc file WAV');
    const data = await fs.readFile(filePath);
    return `data:audio/wav;base64,${data.toString('base64')}`;
  });
  ipcMain.handle('file:save-audio', async (_event, filePath: string) => {
    const source = path.resolve(filePath);
    const result = await dialog.showSaveDialog(window!, { defaultPath: path.basename(source), filters: [{ name: 'WAV Audio', extensions: ['wav'] }] });
    if (result.canceled || !result.filePath) return null;
    await fs.copyFile(source, result.filePath);
    const srtSource = source.replace(/\.wav$/i, '.srt');
    try { await fs.copyFile(srtSource, result.filePath.replace(/\.wav$/i, '.srt')); } catch { /* optional companion */ }
    return result.filePath;
  });
  ipcMain.handle('file:show-in-folder', (_event, filePath: string) => shell.showItemInFolder(path.resolve(filePath)));
  ipcMain.handle('external:open', (_event, url: string) => {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') throw new Error('Chỉ cho phép mở liên kết HTTPS');
    return shell.openExternal(parsed.toString());
  });
  await createWindow();
});

app.on('window-all-closed', () => {
  backend?.stop();
  if (process.platform !== 'darwin') app.quit();
});
