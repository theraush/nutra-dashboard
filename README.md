# NUTRA dashboard

**Live: https://nutra.palmtreemedia.co** — the Vercel app in `app/` (see `app/README.md` and `CLAUDE.md`).

The sections below describe the retired Claude-artifact version (https://claude.ai/artifact/J532xrrPfBJKFUzn2htdg8),
kept for reference.

## Files

| File | What it is |
|---|---|
| `dashboard.html` | The page source. Also what gets published to the Claude artifact. |
| `index.html` | GitHub Pages redirect to the Claude dashboard, written by `update.py`. Don't edit by hand. |
| `update.py` | Swaps fresh numbers into `dashboard.html` and rebuilds `index.html`. |
| `CNAME` | Custom domain for GitHub Pages. |

## How the numbers get updated

The **"NUTRA Dashboard Meta Sync"** scheduled task runs hourly. It:

1. pulls daily Meta numbers per ad account (spend, impressions, link clicks, landing page views),
2. pulls JVZoo checkout visits / sales / refunds / commission per offer and day from the NUTRA Tracker database,
3. writes them to a `payload.json` and runs `python3 update.py payload.json`,
4. republishes `dashboard.html` to the Claude artifact (the sync does not push to GitHub).

Only the block between `// @@DATA_START` and `// @@DATA_END` in `dashboard.html` changes on a sync.
If one source fails, its previous numbers are kept and the page header shows a ⚠ with the reason.

### payload.json format

```json
{
  "asOf": "2026-11-07T09:00:00Z", "today": "2026-11-07", "since": "2026-10-01", "adsSince": "2026-11-05",
  "offers":   [ rows of NUTRA Tracker `products` (key, name, offer, network, ad_account_id, lander_url, buy_links, color,
                status, sort, budget, start_date, warn_at, auto_pause, commission_per_sale, autopaused_at,
                warn_alerted_at, depleted_alerted_at) ],
  "networks": [ {"key": "jvzoo", "name": "JVZoo"} ],
  "notes":    [ {"day": "2026-11-06", "product": null, "text": "..."} ],
  "meta":     { "<offer key>": [ {"date": "...", "spend": 1.2, "impr": 100, "clicks": 3, "lpv": 2} ] | null },
  "ads":      { "<offer key>": [ {"id", "name", "campaign", "adset", "status", "date", "spend", "impr", "clicks", "lpv"} ] | null },
  "jvz":      [ {"product_key": "wellness", "offer": "Synaptril", "day": "2026-11-06", "event": "initiated|purchase",
                "type": "SALE|RFND|null", "n": 1, "commission": 0} ] | null
}
```

`update.py` also writes `actions.json` (never committed): budget alerts and auto-pauses that are due —
`alert_warning`, `alert_depleted` and `pause` per offer, based on spend since each test's start date.
The sync acts on them and records them in NUTRA Tracker so each alert fires once per budget.

Pause rules live on the **NUTRA Settings** Claude artifact (https://claude.ai/artifact/JodMmZTNQmEF95cuqnYVXR, read with the
ArtifactData tool): `rules/*`, `config/automation`, `networks/*`, `log/recent`, `config/sync`. The sync passes them in the
payload as `rules`, `automation`, `ruleLog` (log items, for de-duplication) and `jvzAds` (postback rows with `utm_content`, used to
match checkout visits and sales to ad IDs). `update.py` then adds `pause_ad`, `rule_alert`, `rule_blocked` and `rule_waiting`
actions. Rules only ever pause ads.

Everything a viewer changes on the page (date range, tile choices, table columns, test budgets,
manual sales) is saved in that viewer's browser only.
