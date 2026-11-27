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
  - `lib/infoad.py` (+ `lib/infoad.css`) — the **Information advertorial** page type (kind `info`, design = /demo/info-advertorial-v4):
    Claude sends data, the server draws the animated figures (loop, before_after, product, cost, ingredients) for desktop and phone.
    **Design is LOCKED (Vlad approved v4, Nov 2026): AI photo of someone using the product above the fold (clock drawing
    moves into Change #1; clock is the fallback when there's no photo), product photos in bundle cards.** It's the default page type. Don't change the look,
    colours, fonts or section order without asking him; content/bug fixes are fine.
  - `lib/history.py` — **History** tab: archiving a product pauses its active campaigns, sets `offers.status='archived'`
    (hidden everywhere) and freezes a summary in kv `history/<key>`. Restore sets it active again (ads stay paused).
  - `lib/abtest.py` — **copy A/B tests** on built pages: Claude writes version B (`/api/agent/<page>/variant`), `/p/<slug>`
    splits 50/50 with a sticky cookie, tid gets `~<test><A|B>` (postback strips it into `events.variant`), views in `ab_stats`.
    Hourly sync auto-picks a winner (7+ days, 500+ views each, 95%) when the page has auto on.
  - `lib/heroes.py` — **hero photo options**: Claude casts 5/10 different audience-matched photos, checks each, posts good ones
    to `/api/agent/<page>/hero_option`; the team picks one (`Use this`) or A/B tests 1–2 of them. Audience comes from the new-page form.
    Engines: OpenAI (newest gpt-image model the key has) or Higgsfield SOUL V2 (`HF_API_KEY_ID`/`HF_API_KEY_SECRET`) + OpenAI edit that
    places the real product into the SOUL photo; "mix" alternates.
  - **Custom domains**: `pages.domain` (e.g. brain.example.com). On a non-dashboard Host the router serves only that page at `/`,
    its `/u/` images, tracking beacons and `/api/public/domain-check`; everything else 404s. Vlad points Namecheap nameservers
    to Vercel and adds `example.com` + `*.example.com` in Vercel Domains (steps shown in the page's "Your own domain" box).
  - **Page Studio** (Pages tab detail): one step per screen — Product, Audience, Write, Hero photo, Buy link, Domain, Go live, then
    Grow: Split test (what → B → check & start) and Results; live preview on the right. "Classic view" link keeps the old one-page view.
    New page = 3 steps (Product, Audience, Style & build). Endpoints: `/api/pages/<id>/audience`, `/buy_link`; public() has `headline`, `buy_url`.
  - **Left sidebar** (Nov 2026, Zentra look): the old top bar is styled as a fixed left sidebar (≥861px) / bottom bar (phone).
    Home = Overview. Pages lists pages; the open page's steps are nested under it (`window.psSteps`, `psGoExt`).
  - `lib/accounts.py` — **Ad accounts**: extra Facebook connections (system-user tokens, kv `private/meta/conns`), account→connection
    map (`private/meta/accounts`); `meta.using(acct)` picks the right token. Offer→account = `offers.ad_account_id`; page→offer =
    `pages.offer_key` (studio step "Ad account", `/api/pages/<id>/offer`). API: `/api/accounts` (GET, POST op connect|remove|map|refresh).
  - **Гайд** (Russian how-to for Alex): content `app/guide/ru.json` (chapters → steps with `go: {tab, page, step, sel}`),
    served only by `/api/guide` to emails in kv `config/guide.emails` (default propaganda.tae@gmail.com) + owner preview;
    progress in kv `private/guide/<hash>`. UI = sidebar item "Гайд", checklist, "Показать" spotlight + tour.
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
