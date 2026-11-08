# NUTRA dashboard — notes for Claude

Owner: Master V (Vlad Raush, Scale Calls LLC). Explain things simply; he is a media buyer, not a developer.

## What this is
A dashboard for JVZoo affiliate nutra offers run with Meta ads: Wellness Notes (Synaptril), NeuroSharp, Glpatches.
Live at **https://nutra.palmtreemedia.co** (Vercel project `nutra-dashboard`, team vlad-raush; also
https://nutra-dashboard-taupe.vercel.app). Pushing to `main` deploys automatically.

## Layout
- `app/` — **the live app** (Vercel root directory). Python, one WSGI function, Postgres (Neon).
  - `api/index.py` — router: login/setup/invite pages, `/api/db` (Settings documents), postbacks, `/api/cron`, import, health.
  - `lib/sync.py` — the hourly job: Meta numbers + postback events → `snapshot`, then budget pauses, pause rules, alerts.
  - `lib/engine.py` — the maths (merging data, budget alerts, pause rules, offer check, new-ads alerts).
  - `lib/meta.py` — Meta Graph API with `META_TOKEN` (system user). `lib/postback.py`, `lib/auth.py`, `lib/notify.py`, `lib/db.py`.
  - `lib/pages.py`, `lib/agent.py`, `lib/advertorial.py`, `lib/images.py` — the **Pages** tab: Claude (Managed Agents API,
    `ANTHROPIC_API_KEY`) researches a product and posts page content JSON to `/api/agent/<page>/...` (per-page token); the server
    renders it with the advertorial template and hosts it at `/p/<slug>`. Images via OpenAI (`OPENAI_API_KEY`, optional).
    Skills come from the private repo in `SKILLS_REPO` (+ `SKILLS_GITHUB_TOKEN`), else the built-in brief in `lib/pages.py`.
  - `static/dashboard.html` — the page. `static/shim.js` gives it `window.claude.use('db'|'user')` backed by `/api/db`.
  - `app/README.md` — env vars and routes.
- `dashboard.html` (repo root) — same page, used by the old Claude artifact. **After editing the page, copy it to
  `app/static/dashboard.html`** (they must stay identical). Hosted-only behaviour sits behind `window.NUTRA_HOSTED`.
- `update.py`, `index.html` — the retired Claude-artifact pipeline. Leave alone unless asked.
- `.github/workflows/hourly-sync.yml` — calls `/api/cron` every hour (Vercel free plan only allows a daily cron).
  `/api/cron` runs at most once per 25 min for anonymous callers; signed-in editors can force it ("Sync now").

## Hard rules
- **Meta: only ever PAUSE.** Never activate, create, delete or change budgets/targeting/creatives. `meta.pause()` is the only write.
- Never handle secrets: don't print, copy, commit or type passwords, tokens or the postback key. Env vars
  (`META_TOKEN`, `POSTBACK_KEYS`, `DATABASE_URL`, `OWNER_EMAIL`, …) are set by Vlad in Vercel. The repo is **public**.
- Facebook/Meta browser work happens in his **Dolphin** browser, not other browsers.
- Don't change JVZoo postbacks, DNS (Namecheap) or landing pages without asking.
- Landing pages are separate Lovable projects (wellnestnotes.com, vitalroutinedaily.com, everydaywellnesspicks.com);
  they forward clicks and JVZoo postbacks to `https://nutra.palmtreemedia.co/api/public/postback`.

## Working on it
- Test locally against a throwaway Postgres: `DATABASE_URL=... OWNER_EMAIL=... python -c "..."` with `wsgiref`
  serving `api/index.py:app`; mock `lib.meta` functions instead of calling Meta.
- Check pages at phone width (390px) too — no horizontal scroll.
- Keep commits small; Vercel deploys each push to `main`. Verify with `https://nutra.palmtreemedia.co/api/health`.
- Data that matters lives in Postgres tables `offers`, `events`, `notes`, `budget_events`, `snapshot` and the `kv`
  table (Settings: `rules/*`, `offers/*`, `team/*`, `networks/*`, `config/*`, `log/recent`, `private/postback`).
  Never wipe or rebuild these.
