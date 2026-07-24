/// <reference types="vite/client" />

interface Window {
  desktop?: {
    request: <T = unknown>(method: string, params?: unknown) => Promise<T>;
    selectFile: (options?: unknown) => Promise<string | null>;
    listSrtFiles: (folderPath: string) => Promise<{ folder: string; files: string[] }>;
    selectFolder: () => Promise<string | null>;
    readText: (filePath: string) => Promise<string>;
    readAudio: (filePath: string) => Promise<string>;
    saveAudio: (filePath: string) => Promise<string | null>;
    showInFolder: (filePath: string) => Promise<void>;
    openExternal: (url: string) => Promise<void>;
    onBackendEvent: (handler: (event: unknown) => void) => () => void;
  };
}
