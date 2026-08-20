# Series

A serialised show — Chinese AI animation, in the case this was built for —
arrives as a folder of files named `part1_….mp4`, `part2_….mp4`, and has to go
out one episode at a time, in order, with a caption that reads like an episode
of something rather than a standalone post.

That is the whole feature. It changes nothing about the fan-out: publishing
part 3 creates the same independent `PublishJob` per platform that a one-off
upload does.

## The two things a series adds

**An ordering.** The backlog used to sort by `PublishJob.created_at`. Uploading
eight parts in one batch timestamps them milliseconds apart, in whatever order
the uploads happened to finish, so part 5 could publish before part 3. Series
parts are ordered by `SeriesPart.part_index` and nothing else. The episode
number comes from the filename, parsed by
[`sau/series.py`](../sau/series.py).

**Caption material, written once.** For a serialised show the caption is
overwhelmingly structural — series title, episode number, a pointer to the next
part, a fixed hashtag block — and exactly one line differs between episodes.
So the model is a stored template plus a per-part `hook`.

## Filenames

```
part1_the_awakening.mp4   → episode 1, label "the awakening"
Part 02 - reveal.mp4      → episode 2
ep3_x.mp4                 → episode 3
episode.12.finale.mp4     → episode 12
chapter1_x.mp4            → rejected
part0_x.mp4               → rejected: it would sort ahead of episode 1
```

The separator after the digits is required. Without it `part12_x` and `part1_2x`
are the same string to a lazy matcher, and a series that silently renumbers
itself is worse than one that refuses to parse — so an unparseable name is a
422, never a guess. The console shows the parsed number before anything is
uploaded, and `part_index` can be overridden for the file that was named wrongly
and is not worth re-uploading.

## Caption rendering

`sau/captions/template.py` is pure: strings in, strings out, no database and no
network. It is on the publish path, so it has to work with every generator
switched off, misconfigured, or rate-limited.

| Placeholder | Resolves to |
|---|---|
| `{series}` | The title as it reads in the caption |
| `{series_en}` | The English title, if there is one |
| `{part}` | This episode's number |
| `{total}` | `total_parts` if declared, else how many parts are registered |
| `{next_part}` | The next episode's number; empty on the last one |
| `{next_teaser}` | `next_teaser_template` rendered; empty on the last episode |
| `{hook}` | The one line that varies |
| `{hashtags}` | The hashtag block for the platform being rendered |
| `{synopsis}` | The series synopsis |

`SeriesPartResponse` also carries the asset behind an episode — `size_bytes` and
`storage_key` from registration, and `duration_seconds`/`width`/`height`, which
stay null until the first transcode opens the file. That is the first time
anything reads it, so a part that has never published has a size and nothing
else.

Three rules are worth knowing because they are not obvious:

- **An unknown placeholder is left in the output verbatim.** An operator's typo
  shows up in the preview as itself rather than as a silent hole they have to
  notice the absence of.
- **Empty placeholders close their own line.** A blank `{hook}`, or the final
  episode's blank `{next_teaser}`, would otherwise leave a stranded empty line
  mid-caption. Runs of blank lines collapse to one.
- **Truncation backs up to a word boundary, but only so far.** Chinese runs
  without spaces for whole sentences, so an unguarded backoff could discard
  most of a line looking for a space that is not there. The guard is a fifth of
  the budget.

Caption limits per platform live in `sau.models.CAPTION_LIMITS`, mirroring the
same table in `console/src/domain/platforms.ts`.

### The caption is not in the animation's language

The source is Chinese; the audience reading the caption may not be. `language`
is therefore a per-series field (default `Burmese`), not a global setting — two
shows for two audiences do not have to agree.

A worked example, which is the format this was built against:

```
Template     အပိုင်း ({part}) {series}

             {hook}

             {hashtags}

Renders to   အပိုင်း (1) အစွမ်းထက်ကူးပြောင်းသူနဲ့ စိတ်ဖတ်တဲ့မင်းသား🐻‍❄️🐻‍❄️

             တိရစ္ဆာန်တွေရဲ့ စကားကို နားလည်တဲ့ ... သိလိုက်ရတဲ့အခါ...😂😂

             #MyanmarTiktok #fypviral #တရုတ်ဇာတ်လမ်းတိုများ …
```

Only the middle paragraph is generated. The title line and the hashtag block
are the template, identical on every episode, and `{part}` comes from the
filename. Note there is no `{next_teaser}` here: when the hook itself ends on
the cliffhanger — which is how this style reads — a separate teaser line is
redundant, so the default teaser template is empty.

A series created with only a slug **names itself from its first episode**:
`part1_movieName.mp4` already carries the title, so the descriptive tail of the
filename fills a blank `title_local`. It only ever fills a blank; a title typed
by the operator is never overwritten.

## Drafting the hook

`POST /series/{ref}/generate-hooks` drafts every episode's hook in **one call**.

That is the only interesting decision in the feature. Asked for one caption at
a time, a model cannot write a cliffhanger: it has no idea what part 4 is going
to open with, so every hook comes out as an interchangeable logline. Asked for
all of them at once, against the synopsis, it can build a ladder — part 3 ends
on the question part 4 answers. It is also cheaper by roughly the number of
episodes, which is the smaller reason but not a bad one.

Hooks that already have text are shown to the model as settled unless
`overwrite` is set, so a re-run after adding part 9 extends the arc instead of
rewriting lines the operator already approved.

### Redrafting one episode

`parts: [3]` asks for episode 3 alone — but every other episode still goes into
the prompt with its settled hook. A single redraft therefore lands *between* its
neighbours rather than contradicting them, which is the same reason the whole
series is generated in one call to begin with. Pair it with `overwrite: true`,
or the episode is skipped for already having a hook and the call 409s.

### The style example is the lever

`Series.style_example` holds one real caption in the operator's own voice, and
it goes into the prompt as the house style to match. This does more for output
quality than every other field combined, and the effect grows the less of a
language the model has seen — describing a voice in English and asking for
Burmese produces stilted translation; showing one real Burmese caption produces
something in the same register.

The length default follows from the same place. `DEFAULT_HOOK_MAX_CHARS` is 240,
measured from real captions rather than from the platform limits, which are an
order of magnitude larger than anything anyone reads.

What comes back is always a draft. It lands in `SeriesPart.hook`, the operator
edits it in the console, and the template renders the published text from it.

### Providers

Two, tried in the order given by `CAPTION_PROVIDERS`:

| Provider | Endpoint | Key |
|---|---|---|
| `gemini` | `generativelanguage.googleapis.com` | `GEMINI_API_KEY` |
| `openrouter` | `openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |

Both are plain JSON over HTTPS, so neither brings a vendor SDK with it — the
existing `httpx` dependency and `sau.http.with_retries` are the whole transport
story.

A provider with no key is skipped rather than failing, so listing both and
configuring one is a valid setup. **Every** failure falls through to the next
provider, including an auth failure: one provider's key being wrong is
precisely the case the other exists for. If all of them fail the endpoint
returns 502 — not 500, because the generator is an upstream this service
depends on and its being unavailable is not a bug in here. Nothing on the
publish path is affected; the templates still render, the hooks are just not
drafted.

The Gemini key travels in the `x-goog-api-key` header rather than the `?key=`
query parameter Gemini also accepts, because a URL lands in logs and proxy
traces.

## Scheduling

Slots live in the `schedule_slots` table, not in the n8n Cron node. n8n ticks
every 15 minutes and `POST /schedule/tick` decides whether anything is due, so
moving a slot is an edit in the console rather than a workflow change and a
redeploy.

Defaults are 12:00, 18:00 and 21:00 `Asia/Bangkok`, seeded only into an empty
table — re-running `scripts/init_db.py` never resets a schedule the operator
has since edited.

- **At most once per slot per local day.** `last_fired_on` holds the local date
  a slot last released on, so ticking every minute inside the grace window
  still publishes exactly one asset per slot.
- **A slot fires up to 60 minutes late, then skips.** Better a missed slot than
  a backlog dumped at an hour nobody chose.
- **A slot that comes due with an empty backlog is not stamped as fired**, so it
  stays armed for the rest of its grace window and content added a few minutes
  late still catches the slot it was meant for.
- **Saving the slots re-arms them all.** An operator who has just moved this
  evening's slot means the new time, not "already fired, see you tomorrow".

`GET /schedule/plan` pairs the next firing times with what is queued for them.
The times are computed server-side because the arithmetic is timezone-aware,
and two implementations of a DST rule will eventually disagree about one
evening.

## Endpoints

| Call | Effect |
|---|---|
| `POST /series` | Create one. `slug` is the handle; every other field has a default, and the title fills itself from the first episode's filename. |
| `GET /series` / `GET /series/{ref}` | `ref` is an id **or** a slug. Parts come back in episode order, with the gaps listed. |
| `PATCH /series/{ref}` | Partial. An explicit null only clears `total_parts`. |
| `POST /series/{ref}/parts` | Attach an uploaded object. Episode number from the filename unless overridden. |
| `PATCH /series/{ref}/parts/{id}` | Edit the hook, or renumber. |
| `GET /series/{ref}/parts/{id}/preview` | Render for every platform, through the same function publishing uses. |
| `POST /series/{ref}/generate-hooks` | Draft hooks. `parts: [n]` targets one episode, `overwrite` redrafts settled ones. 502 if no provider answers, 409 if there is nothing to write. |
| `POST /series/{ref}/publish` | Fan out. `schedule: true` (the default) drips them through the backlog. |
| `GET`/`PUT /schedule/slots` | The posting rhythm. PUT replaces the whole set. |
| `GET /schedule/plan` | Next firing times, paired with what is queued. |
| `POST /schedule/tick` | Release whatever is due. What n8n calls. |
| `POST /schedule/slots/reset` | Clear every fired marker, so today's slots can fire again. |

Publishing skips parts that already have jobs rather than rejecting the whole
request: re-running publish after adding part 9 should queue part 9, not refuse
because parts 1–8 already went out.

## What is not here

**No transcription, no vision.** Deriving the caption from the video — Whisper
over the Chinese audio, keyframes to a vision model — was considered and left
out. It reverse-engineers a script you already have, at a per-video cost, for a
caption that is 90% structural anyway. If the source videos ever start coming
from somewhere you did not write, that is the point to revisit it.
