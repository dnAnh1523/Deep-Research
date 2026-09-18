# Deep Research frontend

This directory contains the Vite + React 19 workbench. The development server
expects the FastAPI backend at `http://127.0.0.1:8000` and proxies API/SSE
requests there.

```bash
npm ci
npm run dev
npm run lint
npm run build
```

The container image is built from this directory and served by Nginx. Keep
provider credentials in the backend environment; Vite variables are public and
must never contain API keys.
