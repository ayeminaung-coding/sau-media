# DigitalOcean 1 GB Architecture Plan

This branch defines a low-memory production layout for a 1 GB DigitalOcean
Droplet. The Droplet runs only the application processes. Builds, browser
hosting, media storage, PostgreSQL, and Redis live outside the Droplet.

## Target layout

```text
Cloudflare Pages
  React console
       |
       | HTTPS
       v
DigitalOcean Droplet (1 GB)
  Caddy or Nginx -> API container (:8001 on loopback)
  Facebook worker
  TikTok worker
  systemd timer -> POST /schedule/tick on loopback
       |
       +--> external PostgreSQL (Neon or Supabase)
       +--> external Redis (Upstash TCP/Redis endpoint)
       +--> Cloudflare R2
       +--> Facebook and TikTok APIs
```

The Droplet does not run local PostgreSQL, Redis, n8n, or the console. The
console is static and the schedule tick is a small host timer. n8n remains an
optional integration for approvals and notifications, not a required runtime
service.

## Why this migration

The original Compose file runs six services and builds both Python and Node
images on the host. A 512 MiB or 1 GB host cannot reliably build or run that
stack. Publishing no longer transcodes video, so the workers can reuse the
original R2 object; the remaining memory pressure comes from the stateful
services, n8n, the frontend build, and concurrent image builds.

## Invariants preserved

- One independent publish job remains for each platform and asset.
- `PlatformError.retryable` remains the only queue retry signal.
- Workers still transfer bytes and schedule polling instead of blocking.
- Video bytes still go directly from the browser to R2.
- Schedule state remains in PostgreSQL, not Redis or the timer.
- The timer only calls the existing idempotent `POST /schedule/tick` endpoint.

## Migration phases

### Phase 1: External services

Create a PostgreSQL database and Redis instance outside the Droplet. Set
`DATABASE_URL` and `REDIS_URL` in the production `.env`. Do not expose either
service through the Droplet firewall.

### Phase 2: Prebuilt application images

Build and publish the application image from a laptop or CI. The Droplet must
pull an image; it must not run `docker compose build`. The same image is used
by the API and both workers with different commands.

The image no longer installs ffmpeg because the publishing path reuses the
uploaded R2 source object. Every uploaded video must already meet platform
requirements.

### Phase 3: Lightweight runtime

Deploy `docker-compose.prod.yml`. It contains only the API and the two worker
services, uses external PostgreSQL and Redis, binds the API to loopback, and
restarts services after a host reboot.

### Phase 4: Static console

Build `console/` outside the Droplet and deploy `console/dist` to Cloudflare
Pages. Set `VITE_API_BASE_URL` to the HTTPS API hostname and set the matching
origin in `CORS_ORIGINS`.

### Phase 5: Schedule heartbeat

Install `deploy/systemd/sau-schedule.service` and
`deploy/systemd/sau-schedule.timer`. The timer calls the API every 15 minutes
from localhost. The API continues to decide due slots, ordering, and release;
the timer does not duplicate that logic.

### Phase 6: HTTPS and hardening

Put Caddy or Nginx in front of port 8001. Allow only SSH from the operator IP
and HTTP/HTTPS from the internet. Keep ports 5432, 6379, 5678, 8000, and 8001
private. Do not expose `/schedule/tick` publicly; the host timer calls it via
localhost.

## Rollout checklist

1. Create external PostgreSQL and Redis credentials.
2. Build and push the image from CI or a development machine.
3. Create production `.env` with external service URLs and new platform
   credentials.
4. Run `docker compose -f docker-compose.prod.yml pull` on the Droplet.
5. Run `docker compose -f docker-compose.prod.yml up -d`.
6. Run database initialization once with the API container.
7. Verify `/healthz`, API logs, and both worker processes.
8. Deploy the console to Cloudflare Pages.
9. Install and enable the systemd timer.
10. Run one test upload and one scheduled test post per platform.

## Rollback

Keep the previous image tag. To roll back, set `SAU_IMAGE` to that tag and
run `docker compose -f docker-compose.prod.yml up -d`. Do not delete external
PostgreSQL data or Redis credentials during an application rollback.
