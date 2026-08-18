# Getting Credentials

Every value in `.env`, where it comes from, and how long it lasts.

Work through this in order. Facebook and TikTok are independent — if one is
stuck in review, the other can go live without it. That is the point of the
fan-out design.

> **Portals change.** The API endpoints below are stable and versioned; the
> dashboard menu names are not. If a screen has been renamed, the surrounding
> steps still apply — search the portal for the product name, not the label.

## What you need

| `.env` variable | Source | Lifetime |
|---|---|---|
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Cloudflare dashboard | until revoked |
| `R2_BUCKET`, `R2_PUBLIC_BASE_URL` | Cloudflare dashboard | permanent |
| `TIKTOK_PULL_FROM_URL` | `false` unless you own a verified domain | — |
| `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET` | Meta app settings | permanent |
| `FACEBOOK_PAGE_ID` | Graph API | permanent |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Graph API exchange | **does not expire** (if derived correctly — see step F5) |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | TikTok app credentials | permanent |
| `TIKTOK_ACCESS_TOKEN` | OAuth exchange | **~24 hours**, auto-refreshed |
| `TIKTOK_REFRESH_TOKEN` | OAuth exchange | ~365 days, **rotates on every use** |

The remaining `.env` entries are not credentials and the shipped defaults
work as-is under `docker compose`:

| Variable | Default | Change it when |
|---|---|---|
| `DATABASE_URL` | points at the compose `postgres` service | using an external database |
| `REDIS_URL` | points at the compose `redis` service | using an external Redis |
| `LOG_LEVEL` | `INFO` | debugging — `DEBUG` logs every chunk |
| `FACEBOOK_GRAPH_VERSION` | `v21.0` | Meta deprecates that version |
| `CHUNK_SIZE_BYTES` | 16 MiB | tuning the push path; must stay within TikTok's 5–64 MiB window |

---

# Part 1 — Cloudflare R2

Needed first: both platforms can pull the video from R2, which is the default
and fastest path.

**R1. Create the bucket.**
Cloudflare dashboard → **R2** → *Create bucket*. Name it `sau-media`.
→ `R2_BUCKET=sau-media`

**R2. Find your account ID.**
It is in the R2 overview page sidebar, and in your dashboard URL:
`dash.cloudflare.com/<account-id>/r2`.
→ `R2_ACCOUNT_ID`

**R3. Create an API token.**
**R2** → *Manage R2 API Tokens* → *Create API token*.

Cloudflare offers two kinds. Choose **Account API token**:

| | Account API token | User API token |
|---|---|---|
| Tied to | the account | your personal user |
| Permissions | set explicitly on the token | inherited from your user |
| If you leave the account | keeps working | **stops working** |
| Who can create it | Super Administrators only | any user |

A User token silently dies the day your user is removed or demoted, taking
production down with it. Use an Account token for anything a server runs on.

> Only see the User option? You are not a Super Administrator on that
> Cloudflare account — ask an admin to create the Account token for you.

Then set:

- **Permission: `Object Read & Write`** — enough to read, write, and list
  objects. Do *not* grant `Admin Read & Write`; this service never creates or
  deletes buckets.
- **Scope it to the `sau-media` bucket only.** Bucket scoping is offered for
  the two `Object` permission levels.

You get an **Access Key ID** and a **Secret Access Key**. The secret is shown
**once** — copy it now.
→ `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`

**R4. Make the bucket publicly readable.**

Both platforms can download the video themselves instead of being fed chunks
by your server. That needs a public URL. You have two options, and they are
**not** equivalent.

### Option A — Public Development URL (free, no domain needed)

Bucket → **Settings** → *Public Development URL* → **Enable**.
You get something like `https://pub-<hash>.r2.dev`.

→ `R2_PUBLIC_BASE_URL=https://pub-<hash>.r2.dev`

| Works for | Status |
|---|---|
| **Facebook** (Reels + feed video) | ✅ yes — Meta downloads from any public URL |
| **TikTok** `PULL_FROM_URL` | ❌ **no** — see below |
| Production traffic | ⚠️ Cloudflare rate-limits `r2.dev` and advises against it |

TikTok requires the URL's domain to be **verified in its developer portal**
before it will download from it. Verification proves you own the domain — and
you do not own `r2.dev`, Cloudflare does. Initialising a publish against an
unverified domain fails with HTTP 403 `url_ownership_unverified`.

So on Option A, set `TIKTOK_PULL_FROM_URL=false` (the default) and TikTok will
upload in chunks instead. **This is a fine place to be**: TikTok videos are
small and capped at 10 minutes, so chunked upload costs little. Facebook —
where the files are large — still gets the fast pull path.

### Option B — Custom domain (needs a domain you own)

Bucket → **Settings** → *Custom Domains* → **Add**, e.g.
`media.yourdomain.com`. The domain must already be on Cloudflare DNS.

→ `R2_PUBLIC_BASE_URL=https://media.yourdomain.com`
→ `TIKTOK_PULL_FROM_URL=true` (after completing step **T7**)

Unlocks the pull path for TikTok too, and removes the `r2.dev` rate limit.
A domain costs roughly $5–15/year; this is the only thing it buys you here, so
it is worth it only if TikTok chunked upload actually becomes a bottleneck.

### Verify whichever you chose

```bash
# upload any small file to the bucket first, then:
curl -sI https://<your-public-base>/test.mp4 | head -3
# expect: HTTP/2 200  and  content-type: video/mp4
```

> Leaving `R2_PUBLIC_BASE_URL` empty is also valid. Both platforms then fall
> back to chunked push. It works, but Facebook uploads get much slower and use
> far more of your bandwidth.

---

# Part 2 — Facebook

You need a **Facebook Page** (not a personal profile). Videos publish to a
Page.

**F1. Create the app.**
<https://developers.facebook.com/apps> → *Create App* → use case
**Other** → type **Business**.

**F2. App ID and secret.**
App dashboard → **App settings → Basic**.
→ `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET` (click *Show*, reauthenticate)

**F3. Add the login product.**
Dashboard → *Add product* → **Facebook Login for Business** → *Set up*.

**F4. Get a short-lived User token.**
Open the **Graph API Explorer**:
<https://developers.facebook.com/tools/explorer>

- *Meta App*: your app
- *User or Page*: **User Token**
- Add these permissions:
  - `pages_show_list`
  - `pages_read_engagement`
  - `pages_manage_posts`
  - `publish_video`
  - `business_management` *(only if the Page is owned by a Business Portfolio)*
- Click **Generate Access Token** and approve the dialog.

This token lasts ~1–2 hours. It is an intermediate step, not the final answer.

**F5. Exchange it for a long-lived User token.**

```bash
APP_ID=your_app_id
APP_SECRET=your_app_secret
SHORT_TOKEN=paste_from_step_F4

curl -s "https://graph.facebook.com/v21.0/oauth/access_token\
?grant_type=fb_exchange_token\
&client_id=$APP_ID\
&client_secret=$APP_SECRET\
&fb_exchange_token=$SHORT_TOKEN"
```

Returns a token valid ~60 days. Save it as `LONG_USER_TOKEN`.

> **This step is not optional.** A Page token derived from a *short-lived* user
> token expires in about an hour. A Page token derived from a *long-lived* one
> never expires. Skipping F5 is the single most common reason Facebook
> publishing breaks a day later.

**F6. Get the Page ID and the Page token.**

```bash
LONG_USER_TOKEN=paste_from_step_F5

curl -s "https://graph.facebook.com/v21.0/me/accounts?access_token=$LONG_USER_TOKEN" \
  | python3 -m json.tool
```

Response, one entry per Page you manage:

```json
{ "data": [ { "name": "My Page", "id": "1234567890", "access_token": "EAAG..." } ] }
```

→ `FACEBOOK_PAGE_ID` = that `id`
→ `FACEBOOK_PAGE_ACCESS_TOKEN` = that `access_token`

**F7. Confirm the Page token never expires.**

```bash
PAGE_TOKEN=paste_from_step_F6

curl -s "https://graph.facebook.com/v21.0/debug_token\
?input_token=$PAGE_TOKEN&access_token=$LONG_USER_TOKEN" | python3 -m json.tool
```

Look for **`"expires_at": 0`** — zero means never. Any other number means you
skipped or botched F5; go back and redo it.

Also check `scopes` contains `pages_manage_posts` and `publish_video`.

**F8. App Review.** *(required only for public posting)*
While the app is in **Development mode**, it works fully — but only for users
with a role on the app (admin/developer/tester). That is enough to test the
entire pipeline.

To post publicly you need **Advanced Access** for `pages_manage_posts`,
`publish_video`, and `pages_read_engagement`. App dashboard → *App Review →
Permissions and Features*. Each request needs a screencast showing the
permission in use, plus a privacy policy URL. Allow weeks, not days.

---

# Part 3 — TikTok

**T1. Register as a developer.**
<https://developers.tiktok.com> → sign up, verify email.

**T2. Create an app.**
*Manage apps* → *Create an app*. Fill in name, description, category, icon,
terms and privacy policy URLs. Incomplete fields block the later audit.

**T3. Client key and secret.**
App page → **Credentials** (or *Basic information*).
→ `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`

**T4. Add the Content Posting API.**
App page → *Add products* → **Content Posting API**.
Turn on **Direct Post** — without it you can only push drafts to the user's
inbox, not publish.

**T5. Add scopes.**
Under *Scopes*, enable:
- `user.info.basic` — required; the publisher calls `creator_info` before every post
- `video.publish` — direct posting
- `video.upload` — draft/inbox posting (add if you want the fallback)

**T6. Set a redirect URI.**
Under *Login Kit* / *Redirect URI*, add one. It must be **HTTPS** and match
byte-for-byte at exchange time. `http://localhost` is **not** accepted.

No public HTTPS endpoint? Any URL that renders in your browser works — you
only need to read the `code` out of the address bar. `https://example.com/cb`
is fine as a placeholder.

**T7. Verify your R2 domain.** *(skip unless you chose R4 Option B)*
App page → *URL properties* / *Domain verification*. Add
`media.yourdomain.com` and complete the ownership check.

Only then set `TIKTOK_PULL_FROM_URL=true`. Without it, publishing uses
chunked upload, which needs no verification and no domain at all.

You cannot verify an `r2.dev` URL — that domain belongs to Cloudflare, not
to you. Presigned R2 URLs do not work here either.

**T8. Authorize the account.**
Build the URL (replace the two placeholders, keep everything else):

```
https://www.tiktok.com/v2/auth/authorize/
  ?client_key=YOUR_CLIENT_KEY
  &scope=user.info.basic,video.publish
  &response_type=code
  &redirect_uri=https://example.com/cb
  &state=xyz123
```

Join it into a single line, open it in a browser, log in as the posting
account, approve. You land on your redirect URI with `?code=...` in the
address bar.

> **Copy the `code` exactly, then URL-decode it.** TikTok codes commonly end in
> `%2A`, which is an encoded `*`. Exchanging the encoded form fails with an
> unhelpful error. Replace `%2A` with `*`.

**T9. Exchange the code for tokens.** Do this **within a few minutes** — the
code expires quickly.

```bash
CLIENT_KEY=your_client_key
CLIENT_SECRET=your_client_secret
CODE=paste_url_decoded_code
REDIRECT_URI=https://example.com/cb

curl -s -X POST "https://open.tiktokapis.com/v2/oauth/token/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_key=$CLIENT_KEY" \
  -d "client_secret=$CLIENT_SECRET" \
  -d "code=$CODE" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=$REDIRECT_URI" | python3 -m json.tool
```

Response:

```json
{
  "access_token":  "act.example...",
  "expires_in":    86400,
  "refresh_token": "rft.example...",
  "refresh_expires_in": 31536000,
  "open_id": "...",
  "scope": "user.info.basic,video.publish"
}
```

→ `TIKTOK_ACCESS_TOKEN` = `access_token`
→ `TIKTOK_REFRESH_TOKEN` = `refresh_token`

> **The refresh token is single-use.** Every refresh returns a *new* one and
> invalidates the old. The app handles this under a row lock
> ([sau/tokens.py](../sau/tokens.py)) — but never run a manual refresh with
> `curl` against a live deployment, or you will invalidate the pair the workers
> are holding and have to redo T8–T9.

**T10. Audit.** Until TikTok approves your app, every post is forced to
`SELF_ONLY` regardless of what you request. The publisher reads
`privacy_level_options` from `creator_info` and clamps automatically, logging
`tiktok.privacy.clamped`. Testing works fine in this state — the video appears
private on the account. Submit for audit from the app page.

---

# Part 4 — Load them

```bash
cp .env.example .env
# paste every value in, then:
docker compose up -d --build
docker compose exec api python scripts/init_db.py
```

`init_db.py` creates the tables and copies the tokens from the environment
into the `oauth_tokens` table, which is what the workers actually read. After
that, the TikTok values in `.env` are only a seed — the live token lives in the
database and refreshes itself.

Re-seed at any time after editing `.env`:

```bash
docker compose exec api python scripts/seed_tokens.py
```

---

# Part 5 — Verify before publishing

**Facebook — can you see the Page?**
```bash
curl -s "https://graph.facebook.com/v21.0/$FACEBOOK_PAGE_ID?fields=name,id\
&access_token=$FACEBOOK_PAGE_ACCESS_TOKEN"
```
Returns the Page name → the token works and is scoped to the right Page.

**TikTok — can you query the creator?**
```bash
curl -s -X POST "https://open.tiktokapis.com/v2/post/publish/creator_info/query/" \
  -H "Authorization: Bearer $TIKTOK_ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=UTF-8" | python3 -m json.tool
```
Returns `creator_username` and `privacy_level_options`. If the options list is
only `["SELF_ONLY"]`, the audit has not passed yet — expected, not an error.

---

# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| FB works, then fails ~1h later | Page token derived from a short-lived user token | Redo F5, confirm `expires_at: 0` in F7 |
| FB `code 190` | Token revoked, expired, or password changed | Redo F4–F6 |
| FB `code 200` / permission error | Missing scope, or app still needs Advanced Access | Check `scopes` in F7; see F8 |
| TikTok `access_token_invalid` | Access token past 24h and refresh failed | Check `oauth_tokens` row; re-run T8–T9 |
| TikTok exchange fails immediately | `code` still URL-encoded, expired, or `redirect_uri` mismatch | Decode `%2A` → `*`, redo T8 fast, match the URI exactly |
| TikTok `url_ownership_unverified` (403) | `TIKTOK_PULL_FROM_URL=true` but the domain is unverified — or is an `r2.dev` URL, which can never be verified | Set `TIKTOK_PULL_FROM_URL=false`, or complete R4 Option B + T7 |
| Posts land private on TikTok | App not audited | Expected. Submit for audit (T10) |
| Facebook fails fetching the file URL | `R2_PUBLIC_BASE_URL` wrong, or public access not enabled | Re-check R4 with the `curl -I` |
| TikTok uploads feel slow | Expected on chunked upload | Only fixable via R4 Option B |

# Keeping them safe

- `.env` is gitignored. Keep it that way — the Page token alone is enough to
  post to your Page.
- Scope the R2 token to the single bucket, `Object Read & Write` only, and
  make it an **Account** token so it survives staff changes (see R3).
- Rotate by repeating the relevant part and re-running `scripts/seed_tokens.py`.
- Tokens are stored in plaintext in `oauth_tokens`. Encrypting that column, or
  moving to a secrets manager, is Phase 6 in the
  [implementation plan](IMPLEMENTATION_PLAN.md).
