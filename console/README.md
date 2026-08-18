# Console

The operator UI: pick a video, pick platforms, write one caption per platform,
then either publish immediately or drop it in the daily backlog.

React 19 + TypeScript + Vite. No UI framework, no state library, no CSS
framework — the whole thing is ~220 kB of JS (70 kB gzipped), most of which is
React itself.

```bash
npm install
npm run dev      # http://localhost:5173, talks to VITE_API_BASE_URL
npm run build    # type-check, then emit dist/
```

The API must list the console's origin in `CORS_ORIGINS`, and the R2 bucket
must have a CORS policy (`python scripts/init_r2_cors.py`) — the browser PUTs
to R2 directly.

## Layers

Each layer may import from the ones below it, never sideways or upwards.

| Layer | Owns | Rule |
|---|---|---|
| `src/features/` | one folder per panel — upload, targets, compose, publish, jobs, backlog | Presentational. Receives state and callbacks; never calls the API itself. |
| `src/components/` | Button, Card, Field, Badge, Tabs, Progress, OptionCard | Generic. Knows nothing about publishing. |
| `src/hooks/` | composer state, the publish flow, job polling, backlog, theme | The only place effects live. |
| `src/domain/` | platform rules, job lifecycle, slot maths | Pure functions and tables. No React, no fetch. |
| `src/api/` | wire types, `fetch`, presigned upload | The only place a network call is made. |

`App.tsx` is the one component that knows about more than one feature; it
wires hooks to panels and does nothing else.

Two rules worth keeping:

- **Nothing above `src/api/` touches `fetch` or `XMLHttpRequest`.** The video
  goes browser → R2 with a presigned PUT (`api/upload.ts`); no video byte ever
  reaches the FastAPI process, and that is a service-wide invariant, not a
  console detail.
- **Platform differences live in `domain/platforms.ts`, not in JSX.** Field
  names, character limits, whether a title exists at all, and the privacy
  options are one table. Adding a platform to `sau/platforms/` means adding a
  row there and nothing else.

## Configuration

| Setting | Where | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | build time (`.env`, or the compose build arg `CONSOLE_API_BASE_URL`) | The default the bundle ships with. |
| Endpoint panel | runtime, per browser | Overrides the above, stored in `localStorage`. One static build can be pointed at a laptop, staging, or prod. |
| Theme | runtime, per browser | System / light / dark, from the header. |
| Daily slot label | `src/domain/schedule.ts` | **Display only.** The real schedule is the n8n Cron node; keep the two in step. |

## Deploying

`dist/` is plain static files — any static host works, and the Dockerfile here
is a two-stage build that serves them from nginx. See the hosting table in the
root [README](../README.md#hosting).
