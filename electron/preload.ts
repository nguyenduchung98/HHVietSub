import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('desktop', {
  request: (method: string, params: unknown = {}) => ipcRenderer.invoke('backend:request', method, params),
  selectFile: (options: unknown = {}) => ipcRenderer.invoke('dialog:file', options),
  selectFolder: () => ipcRenderer.invoke('dialog:folder'),
  readAudio: (filePath: string) => ipcRenderer.invoke('file:audio-data', filePath),
  saveAudio: (filePath: string) => ipcRenderer.invoke('file:save-audio', filePath),
  showInFolder: (filePath: string) => ipcRenderer.invoke('file:show-in-folder', filePath),
  openExternal: (url: string) => ipcRenderer.invoke('external:open', url),
  translateWithGem: (params: unknown) => ipcRenderer.invoke('gemini:translate', params),
  openGem: (url: string) => ipcRenderer.invoke('gemini:open', url),
  loginGem: () => ipcRenderer.invoke('gemini:login'),
  cancelGem: () => ipcRenderer.invoke('gemini:cancel'),
  pauseGem: (paused: boolean) => ipcRenderer.invoke('gemini:pause', paused),
  onBackendEvent: (handler: (event: unknown) => void) => {
    const listener = (_: unknown, event: unknown) => handler(event);
    ipcRenderer.on('backend:event', listener);
    return () => ipcRenderer.removeListener('backend:event', listener);
  },
});
