# SiteMonitor frontend

Vite + React + TypeScript + Tailwind + shadcn/ui. See the root `CLAUDE.md` for the full architecture.

```powershell
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
npm run typecheck
npm run lint
npm run build
npm run gen:api    # regenerate src/api/schema.d.ts from the running backend
```

Until the backend exposes its endpoints, the API client serves mock data from `src/api/mock.ts`.
Set `VITE_USE_MOCKS=false` in `.env` to call the real backend.
