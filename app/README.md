# NUTRA dashboard on Vercel

Everything for nutra.palmtreemedia.co: the dashboard behind a login, Settings, sales tracking (postbacks) and the
hourly job that pulls Meta numbers and pauses losing ads. Python (one WSGI function) + Postgres. No Lovable, no Claude.

## Vercel project
- **Root directory:** `app`
- **Database:** Storage → Neon Postgres (sets `DATABASE_URL`). Tables are created on first request.
- **Environment variables**

| Name | What |
|---|---|
| `OWNER_EMAIL` | The owner's login email. First visit asks this person to set a password. |
| `CRON_SECRET` | Long random string. The hourly job calls `/api/cron` with `Authorization: Bearer <CRON_SECRET>`. |
| `META_TOKEN` | Meta system-user token with `ads_read` + `ads_management` on the three ad accounts. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional: alerts by Telegram. |
| `RESEND_API_KEY`, `ALERT_EMAIL`, `ALERT_FROM` | Optional: alerts by email (Resend). |

## Routes
| Route | |
|---|---|
| `/` | Dashboard (login required). Data comes from the last sync (`snapshot` table). |
| `/login`, `/setup`, `/logout` | Sign in; first-run owner password. |
| `/api/db` | Settings documents (rules, offers, team, networks, config…) used by the page through `static/shim.js`. |
| `/api/public/postback`, `/api/public/jvzoo-postback` | Network postbacks + lander click beacons (`key` = Settings → Affiliate networks). |
| `/api/cron` | The hourly sync. Bearer `CRON_SECRET`, or an Editor's "Sync now" button. |
| `/api/admin/import` | Owner only: one-time import of offers, events, notes, settings and the page snapshot. |
| `/api/health` | DB / token check. |

## Hourly schedule
`vercel.json` has a daily cron (allowed on the free Hobby plan). On Pro, change it to `"17 * * * *"`.
On Hobby, an external scheduler (e.g. cron-job.org) calls `https://nutra.palmtreemedia.co/api/cron` hourly with the
`Authorization: Bearer <CRON_SECRET>` header.

## Meta safety
The app only ever sets campaigns/ads to PAUSED (`lib/meta.py: pause`). It never activates, creates, or edits budgets.

## Editing the page
`static/dashboard.html` is the page (same file as `../dashboard.html`; copy after edits). Hosted-only behaviour is
behind `window.NUTRA_HOSTED`.
