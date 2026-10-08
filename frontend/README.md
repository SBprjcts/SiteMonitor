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
`watches` mocks only those sections. Every section now has real endpoints, so against the real
backend use `VITE_USE_MOCKS=false`.

Login is only mocked when every section is (you're signed in as a fake admin). As soon as one
section uses the real backend, login is real too: create an account on the login page, then run
`uv run python -m app.make_admin <email>` in `backend/` if you need the store on/off switches.
