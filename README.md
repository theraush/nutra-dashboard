# NUTRA dashboard

Live at **https://nutra.palmtreemedia.co** (GitHub Pages) and as a Claude artifact
(https://claude.ai/artifact/J532xrrPfBJKFUzn2htdg8). Both show the same page.

## Files

| File | What it is |
|---|---|
| `dashboard.html` | The page source. Also what gets published to the Claude artifact. |
| `index.html` | GitHub Pages copy, built from `dashboard.html` by `update.py`. Don't edit by hand. |
| `update.py` | Swaps fresh numbers into `dashboard.html` and rebuilds `index.html`. |
| `CNAME` | Custom domain for GitHub Pages. |

## How the numbers get updated

The **"NUTRA Dashboard Meta Sync"** scheduled task runs hourly. It:

1. pulls daily Meta numbers per ad account (spend, impressions, link clicks, landing page views),
2. pulls JVZoo checkout visits / sales / refunds / commission per offer and day from the NUTRA Tracker database,
3. writes them to a `payload.json` and runs `python3 update.py payload.json`,
4. commits and pushes (GitHub Pages redeploys in ~1 minute), then republishes `dashboard.html` to the artifact.

Only the block between `// @@DATA_START` and `// @@DATA_END` in `dashboard.html` changes on a sync.
If one source fails, its previous numbers are kept and the page header shows a ⚠ with the reason.

### payload.json format

```json
{
  "asOf":  "2026-11-07T09:00:00Z",          // when the pull ran (ISO)
  "today": "2026-11-07",                    // last date Meta returned (ad account day)
  "since": "2026-10-01",                    // first date requested from Meta
  "meta": {                                  // one list per product; null = that account failed
    "wellness": [{"date": "2026-11-06", "spend": 182.58, "impr": 1268, "clicks": 38, "lpv": 29}],
    "neuro":    [ ... ],
    "glp":      [ ... ]
  },
  "jvz": [                                   // rows from NUTRA Tracker; null = query failed
    {"offer": "Synaptril", "day": "2026-11-06", "event": "initiated", "type": null, "n": 1, "commission": 0},
    {"offer": "GLPatches", "day": "2026-11-06", "event": "purchase",  "type": "SALE", "n": 1, "commission": 48.50}
  ]
}
```

Products: `wellness` = Wellness Notes ad account `1614901483744859` (offer Synaptril),
`neuro` = NeuroSharp `1105909655657509`, `glp` = Glpatches `1148819018097191` (offer GLPatches).
Meta days are rows with `spend`/`impr`/`clicks`/`lpv` from fields `amount_spent`, `impressions`,
`link_click`, `omni_landing_page_view` (null counts → 0).

Everything a viewer changes on the page (date range, tile choices, table columns, test budgets,
manual sales) is saved in that viewer's browser only.
