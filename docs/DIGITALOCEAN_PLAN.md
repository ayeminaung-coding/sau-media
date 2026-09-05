# DigitalOcean Deployment Plan

This plan deploys the complete stack on one DigitalOcean Droplet: FastAPI,
the two RQ workers, Postgres, Redis, n8n, and the React console. Cloudflare R2
remains the media store.

## Budget path: maximum $5 for one month

DigitalOcean currently lists a Basic shared-CPU Droplet with 512 MiB RAM at
$4/month. It leaves roughly $1 of a $5 budget, but it is too small for the
complete Compose stack and ffmpeg. Treat it as a temporary learning or smoke-
test server, not a production publisher.

### Create the $4 Droplet

1. Open **Create → Droplets** in the DigitalOcean control panel.
2. Select an Ubuntu LTS image.
3. Select **Basic → Regular Intel or AMD → 512 MiB / 1 vCPU / 10 GiB**.
4. Choose one Droplet only. Do not add backups, block storage, a load
  balancer, a reserved IP, or Marketplace add-ons.
5. Add an SSH key and disable password authentication.
6. Choose the nearest region and give the Droplet a clear name such as
  `sau-test`.
7. Create a Cloud Firewall before using the server. Allow SSH only from your
  own IP and allow HTTP/HTTPS only if you have a domain. Do not open ports
  `5432`, `6379`, `5678`, `8001`, or `8080` to the internet.
8. Set a billing alert at or below `$4` and check the Billing page after
  creation. DigitalOcean bills Droplets hourly, so destroy the Droplet when
  the test is finished rather than leaving it running.

### Use the $4 Droplet safely

SSH to the server and install only the base tools:

```bash
ssh root@<droplet-ip>
apt update && apt upgrade -y
apt install -y git ca-certificates curl
```

For this budget, do **not** run the full command below:

```bash
docker compose up -d --build
```

That command starts Postgres, Redis, n8n, the API, two workers, and the
console together; 512 MiB is not enough for that workload and ffmpeg may be
killed by the operating system. Use the Droplet to test SSH, Docker, DNS,
firewall rules, and HTTPS, while hosting the static console on a free static
host and keeping media in R2.

If you need to test actual publishing, first upgrade to at least the 4 GB
Droplet. Do not rely on swap as a replacement for RAM during video
transcoding. The $4 server is useful preparation, but it is not a dependable
deployment for this repository.

### Stop the budget meter

When finished testing:

1. Export any logs or configuration you need.
2. Confirm the Droplet is no longer needed.
3. Destroy it from the DigitalOcean control panel.
4. Confirm there are no remaining volumes, snapshots, reserved IPs, or other
  billable resources.

The safest $5 plan is therefore: create one `$4` test Droplet, spend no money
on add-ons, validate the server setup, then destroy it. Save production
deployment for when at least `$24/month` is available for a 2 vCPU / 4 GB
Droplet.

## 1. Target architecture

```text
app.example.com  --> Caddy --> console container (:8080)
api.example.com  --> Caddy --> FastAPI container (:8001)
n8n.example.com  --> Caddy + access control --> n8n container (:5678)

Droplet private network:
  API, Facebook worker, TikTok worker, Postgres, Redis, n8n

Browser ----------------------------------------------> Cloudflare R2
Social platforms -------------------------------------> Cloudflare R2
```

Start with one Droplet. Split Postgres and Redis into DigitalOcean managed
services only when backups, high availability, or independent scaling justify
the additional cost and configuration.

## 2. Create the Droplet

- Region: close to the operator and the target platform APIs.
- Image: Ubuntu LTS.
- Size: minimum 2 vCPU and 4 GB RAM; use 8 GB if transcoding videos in
  parallel or running several n8n workflows.
- Disk: at least 80 GB SSD, with free space for source files and ffmpeg
  renditions.
- Authentication: SSH key only; do not enable password login.
- Add a DigitalOcean Cloud Firewall allowing:
  - TCP `22` from the operator's IP range only
  - TCP `80` and `443` from anywhere
  - no public access to `5432`, `6379`, `5678`, `8001`, or `8080`

Reserve a Floating IP if replacing the Droplet without changing DNS is
important.

## 3. Prepare the host

SSH to the Droplet and install Docker from Docker's official Ubuntu
instructions. Then clone the repository:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git ca-certificates curl
git clone <repository-url> /opt/socials-auto-upload
cd /opt/socials-auto-upload
```

Create a non-root deployment user, add it to the `docker` group, and use that
user for normal deployments. Keep `/opt/socials-auto-upload/.env` readable
only by that user:

```bash
cp .env.example .env
chmod 600 .env
```

## 4. Configure DNS and HTTPS

Create DNS records pointing to the Droplet:

- `app.example.com` for the console
- `api.example.com` for FastAPI
- `n8n.example.com` only if n8n must be reached remotely

Install Caddy on the host and proxy the first two names to `127.0.0.1:8080`
and `127.0.0.1:8001`. Caddy obtains and renews Let's Encrypt certificates.
Protect n8n with an authentication layer and expose it only when needed.

Before going live, bind the Compose ports to loopback or remove public port
publishing for internal services. The current Compose file publishes several
ports for local development, so the production deployment must not leave
Postgres or Redis reachable from the internet.

## 5. Fill production environment values

Copy values from [CREDENTIALS.md](CREDENTIALS.md) into `.env`, then set the
deployment-specific values:

```env
DATABASE_URL=postgresql+psycopg://sau:<strong-password>@postgres:5432/sau
REDIS_URL=redis://redis:6379/0

R2_PUBLIC_BASE_URL=https://media.example.com
TIKTOK_PULL_FROM_URL=false

CORS_ORIGINS=["https://app.example.com"]
CONSOLE_API_BASE_URL=https://api.example.com
```

Use an R2 custom domain if TikTok pull uploads are needed. An `r2.dev` URL is
acceptable for Facebook, but TikTok requires a verified custom domain; leave
`TIKTOK_PULL_FROM_URL=false` otherwise.

Use strong, unique values for the database password and every platform/API
credential. Do not commit `.env` or paste secrets into deployment logs.

## 6. First deployment

From the repository directory:

```bash
docker compose up -d --build
docker compose ps
docker compose exec api python scripts/init_db.py
docker compose exec api python scripts/init_r2_cors.py
```

The console image bakes `CONSOLE_API_BASE_URL` into the frontend at build
time, so rebuild the console after changing that value:

```bash
docker compose up -d --build console api worker-facebook worker-tiktok
```

Import the workflow from `n8n/slot-tick.workflow.json`, configure its API URL
as `http://api:8000`, and verify that the n8n heartbeat can reach the API over
the Compose network.

## 7. Verification checklist

Run these checks before adding production credentials or publishing real media:

```bash
curl -fsS https://api.example.com/healthz
docker compose ps
docker compose logs --tail=100 api worker-facebook worker-tiktok
```

Then verify, in order:

1. The console loads at `https://app.example.com`.
2. Browser requests to the API succeed without CORS errors.
3. A small test object can be uploaded directly to R2.
4. `POST /assets/upload-url` returns a presigned URL.
5. A test asset creates independent Facebook and TikTok jobs.
6. Each worker consumes only its own queue and schedules polling.
7. A failed platform job can be retried without changing the other platform's
   state.
8. n8n releases a scheduled test item once and does not duplicate it.

Use a test Page and TikTok account first. The platform request shapes in this
repository have not been verified against live APIs; follow the checklist in
[PLATFORM_NOTES.md](PLATFORM_NOTES.md) before production publishing.

## 8. Backups and operations

- Back up the Postgres volume daily and retain several recent copies off the
  Droplet. A Droplet snapshot alone is not a sufficient database backup.
- Back up `/var/lib/docker/volumes/` data for Postgres, Redis, and n8n only
  while the services are stopped or through database-aware tools.
- R2 is the source of media; configure lifecycle rules for old renditions and
  failed uploads.
- Monitor disk usage because ffmpeg uses temporary local space:

  ```bash
  df -h
  docker system df
  docker compose logs -f worker-facebook worker-tiktok
  ```

- Apply OS and image updates during a maintenance window:

  ```bash
  git pull
  docker compose up -d --build
  docker image prune
  ```

- Keep the Docker Compose project enabled after reboots with a systemd unit or
  an equivalent restart policy.

## 9. Rollback and recovery

Before each deployment, record the deployed Git commit and make a database
backup. To roll back application code:

```bash
git checkout <known-good-commit>
docker compose up -d --build
```

Do not delete the Postgres, Redis, or n8n volumes during an application
rollback. If the Droplet is lost, provision a replacement, restore Postgres,
restore the n8n data, attach the same R2 credentials, and point the DNS records
to the replacement IP.

## 10. Completion criteria

The deployment is ready when HTTPS works for the console and API, internal
ports are not internet-accessible, the R2 browser upload succeeds, both workers
run independently, n8n can reach the API, backups have been restored once in a
test environment, and one real test post succeeds on each platform.