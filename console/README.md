# Console

The operator UI: pick a video, pick platforms, write one caption per platform,
then either publish immediately or drop it in the backlog. The Series view does
the same for a serialised show — many episodes, one caption template, released
one part per slot. A sidebar switches between them and the other views.

React 19 + TypeScript + Vite. No UI framework, no state library, no CSS
framework — the whole thing is ~250 kB of JS (78 kB gzipped), most of which is
React itself.

```bash
npm install
npm run dev      # http://localhost:5173, talks to VITE_API_BASE_URL
npm run build    # type-check, then emit dist/
```

The API must list the console's origin in `CORS_ORIGINS`, and the R2 bucket
must have a CORS policy (`python scripts/init_r2_cors.py`) — the browser PUTs
to R2 directly.

`npm run dev` serves from `http://localhost:5173`, which is a different origin
from the deployed console on `:8080`. Both belong in `CORS_ORIGINS`, and the
R2 script must be re-run after adding one — otherwise the presign succeeds and
the upload dies at the bucket's preflight instead.

## Layers

Each layer may import from the ones below it, never sideways or upwards.

| Layer | Owns | Rule |
|---|---|---|
| `src/features/` | one folder per panel — upload, targets, compose, publish, jobs, backlog, series, schedule, nav | Presentational. Receives state and callbacks; never calls the API itself. |
| `src/components/` | Button, Card, Field, Badge, Tabs, Progress, OptionCard | Generic. Knows nothing about publishing. |
| `src/hooks/` | composer state, the publish flow, job polling, backlog, series, schedule, theme | The only place effects live. |
| `src/domain/` | platform rules, job lifecycle, series naming, schedule formatting, the view list | Pure functions and tables. No React, no fetch. |
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
- **Caption rendering is not mirrored here.** The episode preview comes from
  `GET /series/{ref}/parts/{id}/preview`, rendered by the same function the
  publish path calls, so what the operator reads cannot drift from what
  publishes. `domain/series.ts` mirrors only the *filename* parser, so a dropped
  file shows its episode number without a round trip — and the server re-parses
  the name it is sent regardless.

## Series

`features/series/` is the serialised-show view: drop `part1_….mp4`,
`part2_….mp4`, and each file's episode number is read from its name. Uploads
run one at a time, in episode order rather than drop order, so a batch that
fails halfway still leaves a contiguous run.

The caption is a template written once per series plus a one-line `hook` per
episode, edited in place in the parts table. **Draft missing hooks** asks the
API to write every episode's hook in one call, which is what lets part 3 end on
the question part 4 answers; it is always a draft, and nothing publishes
without the operator reading it.

## Schedule

The posting slots are server state, edited in `features/schedule/SlotEditor`
under the Backlog view. There is no slot constant in the app any more: the
times come from `GET /schedule/slots` and the upcoming firing times from
`GET /schedule/plan`, because that arithmetic is timezone-aware and a second
implementation of a DST rule in the browser would eventually disagree with the
one that actually releases.

## Navigation

`src/domain/navigation.ts` is the list of views: label, group, icon, one line
of description, and whether the view is built. Adding a row puts an item in the
sidebar; `Sidebar.tsx` renders whatever is in the table and knows nothing else.

A row with `locked: true` is a feature that is planned but not written. It is
still selectable — it renders `ComingSoon`, which states plainly that nothing
on the page is wired up and lists what the view will do, from the row's
`plans`. An operator should never have to guess whether an empty panel is a
plan or a page that failed to load. Building the view means deleting `locked`
and `plans` and adding its branch in `App.tsx`.

The selected view is remembered in `localStorage` (`sau.view`) by `useNav`.
Every hook stays mounted in `App.tsx` rather than inside a view, so switching
away from Jobs does not drop a poll that is in flight.

## Configuration

| Setting | Where | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | build time (`.env`, or the compose build arg `CONSOLE_API_BASE_URL`) | The default the bundle ships with. |
| Endpoint panel | runtime, per browser | Overrides the above, stored in `localStorage`. One static build can be pointed at a laptop, staging, or prod. |
| Theme | runtime, per browser | System / light / dark, from the header. |
| Posting slots | Backlog → Schedule, at runtime | Stored server-side. Editing them takes effect on the next tick; n8n only supplies the heartbeat. |

## Deploying

`dist/` is plain static files — any static host works, and the Dockerfile here
is a two-stage build that serves them from nginx. See the hosting table in the
root [README](../README.md#hosting).
