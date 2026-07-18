import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const utf8Headers = () => ({
  name: 'hhvietsub-utf8-headers',
  configureServer(server: any) {
    server.middlewares.use((_request: any, response: any, next: () => void) => {
      const writeHead = response.writeHead.bind(response);
      response.writeHead = (...args: any[]) => {
        const contentType = response.getHeader('Content-Type');
        if (typeof contentType === 'string' && /^(text\/|application\/(javascript|json))/.test(contentType) && !/charset=/i.test(contentType)) {
          response.setHeader('Content-Type', `${contentType}; charset=utf-8`);
        }
        return writeHead(...args);
      };
      next();
    });
  },
});

export default defineConfig({
  plugins: [utf8Headers(), react()],
  server: { port: 5173, strictPort: true },
});
