import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('desktop', {
  request: (method: string, params: unknown = {}) => ipcRenderer.invoke('backend:request', method, params),
  selectFile: (options: unknown = {}) => ipcRenderer.invoke('dialog:file', options),
  listSrtFiles: (folderPath: string) => ipcRenderer.invoke('folder:srt-files', folderPath),
  selectFolder: () => ipcRenderer.invoke('dialog:folder'),
  readText: (filePath: string) => ipcRenderer.invoke('file:text-data', filePath),
  readAudio: (filePath: string) => ipcRenderer.invoke('file:audio-data', filePath),
  saveAudio: (filePath: string) => ipcRenderer.invoke('file:save-audio', filePath),
  showInFolder: (filePath: string) => ipcRenderer.invoke('file:show-in-folder', filePath),
  openExternal: (url: string) => ipcRenderer.invoke('external:open', url),
  onBackendEvent: (handler: (event: unknown) => void) => {
    const listener = (_: unknown, event: unknown) => handler(event);
    ipcRenderer.on('backend:event', listener);
    return () => ipcRenderer.removeListener('backend:event', listener);
  },
});
