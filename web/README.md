# web

The VISUALISER web app: React 19, TypeScript, Vite 8, Tailwind 4 and Motion. It runs on the phone, which is the camera, and talks only to its own origin (`/api`).

```text
src/lib/        api client (contract-validated), recorder, flow state machine, kinetic timing, error copy
src/hooks/      useCamera: permissions, front/back switch, stops when hidden
src/components/ camera stage with countdown and progress ring, review, processing, result, errors
```

Flow: intro → camera (3-2-1 countdown, ≤10 s) → review → processing → kinetic result, with recovery copy for every camera problem and API error code.

## Commands

All commands run from `web/`.

```bash
npm install
```

```bash
npm test
```

```bash
npm run build
```

`npm run build` writes `dist/`, which `backend-go` serves at `/`.

```bash
npm run dev
```

The dev server listens on :5173 and proxies `/api` to Go on :8080.
