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

The API client can serve mock data from `src/api/mock.ts`, per section. `VITE_USE_MOCKS` in `.env`
controls it: `true` (default) mocks everything, `false` mocks nothing, and a list such as
`watches` mocks only those sections. Stores and products have real endpoints; watches don't yet,
so against the real backend use `VITE_USE_MOCKS=watches`.
