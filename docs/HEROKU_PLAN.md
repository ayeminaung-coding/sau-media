# Heroku deployment plan — $13/month student credit

Target: run the whole pipeline inside the GitHub Student Developer Pack's
**$13/month for 24 months** Heroku credit, with $0 out of pocket.

Legend: `[ ]` to do · `[!]` needs a code change in this repo.

Read [DEPLOYMENT.md](DEPLOYMENT.md) first for why this option exists and what
it costs you relative to a plain VM.

---

## The budget

| Item | Plan | Monthly |
|---|---|---|
| Dynos | Eco (1000 shared dyno-hours) | $5 |
| Postgres | `heroku-postgresql:essential-0` (1 GB, 10M rows) | $5 |
| Redis | `heroku-key-value-store:mini` (25 MB) | $3 |
| Cron | Heroku Scheduler | $0 |
| Console | Cloudflare Pages | $0 |
| Media | Cloudflare R2 | $0 |
| **Total** | | **$13** |

Exactly the credit, with no headroom. Anything added — a second dyno size, a
larger Postgres, papertrail — comes out of pocket.

## Shape of the deployment

Two Heroku apps from one repo, sharing one set of add-ons:

- **`sau-api`** — `web` dyno only. Sleeps after 30 minutes without traffic.
- **`sau-worker`** — `worker` dyno only. An app with no web dyno never
  sleeps, so the RQ worker stays up and `with_scheduler=True` keeps firing the
  `enqueue_in` polls that `sau/queue/tasks.py` depends on.

Two apps rather than one because in a single app the worker sleeps whenever
the web dyno does, and a sleeping worker is a stalled publish queue.

Both platform queues run in **one** worker process (`python scripts/worker.py`
with no arguments takes every queue). This is a dyno-hour concession, not a
design change: jobs stay one-per-platform in the database and invariant 1 is
untouched. What is lost is the isolation compose provides — a 4 GB Facebook
transfer now delays a TikTok post behind it in the same worker.

### Dyno-hour arithmetic

| | Hours/month |
|---|---|
| `sau-worker`, always on | ~730 |
| `sau-api`, waking for ticks and console use | ~120–250 |
| **Total** | **~850–980 of 1000** |

Thin. Two rules follow:

- Do **not** add a keep-alive pinger to `sau-api`. Letting it sleep is what
  makes the budget work; the console and the cron both wake it on demand.
- Keep the tick schedule coarse. A tick every 10 minutes holds the web dyno
  awake permanently and blows the ceiling on its own.

When the 1000 hours are exhausted, **all** Eco dynos stop until the next
billing month — publishing stops with them. Watch it in the dashboard.

## Phase 0 — Accounts

- [ ] Claim the Heroku offer in the Student Pack; confirm the credit shows on
      the billing page. It is $13/mo for 24 months, not a lump sum, and it
      does not roll over.
- [ ] Verify the Heroku account with a card (required even under credit).
- [ ] `heroku login` and `heroku container:login` locally.

## Phase 1 — Code changes `[!]`

Three things the platform forces, all in `sau/config.py`. None of them change
behaviour anywhere else, and all are safe locally.

- [!] **Normalise `DATABASE_URL`.** Heroku injects `postgres://…`, which
      SQLAlchemy 2.0 rejects, and the repo needs the psycopg 3 driver
      explicitly. Rewrite it in a field validator rather than pinning the URL
      as a config var — Heroku rotates Postgres credentials without notice and
      a hardcoded copy will break on rotation:

      ```python
      @field_validator("database_url")
      @classmethod
      def _normalise_database_url(cls, v: str) -> str:
          # Heroku injects the legacy postgres:// prefix and no driver.
          if v.startswith("postgres://"):
              v = "postgresql://" + v[len("postgres://"):]
          if v.startswith("postgresql://"):
              v = "postgresql+psycopg://" + v[len("postgresql://"):]
          return v
      ```

- [!] **Accept Heroku's Redis TLS certificate.** Key-Value Store serves
      `rediss://` with a self-signed certificate; redis-py refuses it by
      default and every enqueue fails at connect. Append
      `?ssl_cert_reqs=none` to the URL in a validator when the scheme is
      `rediss` and no `ssl_cert_reqs` is present.

- [!] **Bind the port Heroku assigns.** The Dockerfile's `CMD` hardcodes
      8000; the web dyno must listen on `$PORT`. Fixed in `heroku.yml` (next
      phase) rather than in the Dockerfile, so compose keeps its fixed port.

Add a test for the URL normalisation — it is pure string logic, which is
exactly what `pytest` covers here.

## Phase 2 — App setup

- [ ] Add `heroku.yml` at the repo root:

      ```yaml
      build:
        docker:
          web: Dockerfile
          worker: Dockerfile
      run:
        web: uvicorn sau.api.main:app --host 0.0.0.0 --port $PORT
        worker: python scripts/worker.py
      ```

      Container stack, not buildpacks: the image already carries ffmpeg and
      the API and worker are meant to share it.

- [ ] Create both apps and set the stack:

      ```bash
      heroku create sau-api    --stack container
      heroku create sau-worker --stack container
      ```

- [ ] Provision add-ons on `sau-api` and attach them to `sau-worker` so both
      processes share one database and one Redis:

      ```bash
      heroku addons:create heroku-postgresql:essential-0    -a sau-api
      heroku addons:create heroku-key-value-store:mini      -a sau-api
      heroku addons:attach sau-api::DATABASE  -a sau-worker
      heroku addons:attach sau-api::REDIS     -a sau-worker
      ```

- [ ] Set the Redis eviction policy to `noeviction`. RQ stores job state in
      Redis; under an LRU policy a busy moment silently drops jobs rather than
      failing them.

      ```bash
      heroku redis:maxmemory --policy noeviction -a sau-api
      ```

- [ ] Copy every credential from `.env` into config vars on **both** apps
      (`heroku config:set -a …`). `DATABASE_URL` and `REDIS_URL` come from the
      add-ons; everything else in `.env.example` is set by hand.

- [ ] Set `R2_PUBLIC_BASE_URL`. On a shared-CPU dyno this is not an
      optimisation, it is the difference between working and timing out.

- [ ] Set `CORS_ORIGINS` to the Cloudflare Pages origin (phase 4).

## Phase 3 — First deploy

- [ ] Push both apps and scale each to exactly one process type:

      ```bash
      git push heroku-api main && git push heroku-worker main
      heroku ps:scale web=1 worker=0 -a sau-api
      heroku ps:scale web=0 worker=1 -a sau-worker
      ```

      `worker=0` on the API app matters: a stray worker dyno there doubles the
      hour burn and re-introduces the sleep coupling the split exists to avoid.

- [ ] Initialise the schema and seed credentials:

      ```bash
      heroku run python scripts/init_db.py -a sau-api
      ```

      There is no Alembic directory in the repo yet, so this is the migration
      path. If one is added, move it to a `release:` phase in `heroku.yml`.

- [ ] `heroku run python scripts/init_r2_cors.py -a sau-api` after
      `CORS_ORIGINS` is final. Re-run whenever it changes.

- [ ] Check `/health` and confirm `worker.starting` appears in
      `heroku logs -t -a sau-worker`.

## Phase 4 — Console

- [ ] Build `console/` on Cloudflare Pages with
      `VITE_API_BASE_URL=https://sau-api.herokuapp.com`. Do not put it on a
      dyno — it is static, and a second web dyno does not fit the budget.
- [ ] Add that Pages origin to `CORS_ORIGINS` and re-run `init_r2_cors.py`.
- [ ] First page load after an idle period takes a few seconds while the web
      dyno wakes. Expected, not a fault.

## Phase 5 — The scheduled tick

n8n does not fit the budget — it needs its own always-on process and a volume.
`POST /schedule/tick` is a plain HTTP call, so anything that can make one on a
timer replaces it. `n8n/slot-tick.workflow.json` documents the same request.

- [ ] Drive it from a **GitHub Actions** scheduled workflow. Free, real cron
      expressions, and it lives beside the code:

      ```yaml
      on:
        schedule:
          - cron: "0 3,11 * * *"   # UTC; match your ScheduleSlot rows
      jobs:
        tick:
          runs-on: ubuntu-latest
          steps:
            - run: curl -fsS -X POST "$SAU_API_URL/schedule/tick"
              env:
                SAU_API_URL: ${{ secrets.SAU_API_URL }}
      ```

- [ ] Alternative: Heroku Scheduler (free add-on), limited to every 10
      minutes / hourly / daily. Use **daily or hourly only** — the 10-minute
      option keeps the web dyno permanently awake and breaks the hour budget.
- [ ] Either way, the first call after idle wakes the dyno; the request may
      take several seconds. `tick` is idempotent within a slot's day
      (`ScheduleSlot.last_fired_on`), so a retry on timeout is safe.

## Known limits

- **Ephemeral disk, ~1 GB.** `render_for` holds the source and the output in
  the same temp directory, so the practical source ceiling is roughly 400 MB.
  Larger files will fail the transcode on disk, not on memory. Keep sources
  small, or transcode before upload.
- **Shared CPU.** An Eco dyno is one shared vCPU. A long 1080p transcode takes
  minutes and will feel broken next to a local run. RQ's queue timeout is
  already 3600s (`sau/queue/__init__.py`), so it has room.
- **512 MB RAM.** ffmpeg streams, so this is usually survivable — but an R14
  memory warning in the logs is the first thing to check on an unexplained
  worker restart.
- **No queue isolation.** One worker serves both queues, so a large Facebook
  transfer delays TikTok posts behind it. Restore the split by scaling a
  second worker app the moment the budget allows.
- **Ephemeral filesystem.** Nothing on the dyno survives a restart, and dynos
  restart daily. Everything durable is already in Postgres or R2, so this is
  fine — do not add a local cache that assumes otherwise.

## Exit

The credit ends 24 months after it is claimed. At that point the same
configuration costs $13/month. The migration path is
[Oracle Cloud](DEPLOYMENT.md#option-1--oracle-cloud-always-free-vm-recommended):
`pg_dump` the database, restore into the compose Postgres, re-point
`CONSOLE_API_BASE_URL`, and the split-app concessions above go away.

Sources: [Eco dyno hours](https://devcenter.heroku.com/articles/eco-dyno-hours) ·
[Heroku container registry & runtime](https://devcenter.heroku.com/articles/build-docker-images-heroku-yml) ·
[GitHub Student Developer Pack](https://education.github.com/pack)
