# Campus Customs Desk: dashboard

React + Vite + TypeScript dashboard for the Campus Customs agents. It talks to the FastAPI backend at `http://localhost:8000`.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + production build
```

To point it at a different backend, copy `.env.example` to `.env` and set `VITE_API_URL`.

See the main [README](../README.md) for the whole system, and [output/design.md](../output/design.md) for the design.
