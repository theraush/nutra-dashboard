#!/usr/bin/env python3
"""Refresh the numbers in dashboard.html, rebuild index.html, and work out budget alerts / auto-pauses.

    python3 update.py payload.json   # merge fresh data, rebuild, write actions.json
    python3 update.py --build        # only rebuild index.html from dashboard.html

dashboard.html is the page, published to the claude.ai artifact; index.html is a GitHub Pages redirect to that artifact.
Only the block between "// @@DATA_START" and "// @@DATA_END" is rewritten. See README.md for the payload format.
"""
import json, re, sys, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
SRC, OUT, ACT = (os.path.join(HERE, f) for f in ('dashboard.html', 'index.html', 'actions.json'))
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}img{max-width:100%}[hidden]{display:none!important}</style>
'''


def fail(msg):
    print('ERROR:', msg, file=sys.stderr)
    sys.exit(1)


def read_page():
    s = open(SRC, encoding='utf-8').read()
    a, b = s.find('// @@DATA_START'), s.find('// @@DATA_END')
    if a < 0 or b < 0:
        fail('data markers not found in dashboard.html')
    m = re.search(r'const DATA = (\{.*?\});\n', s[a:b], re.S)
    if not m:
        fail('could not find "const DATA = {...};" between the markers')
    return s, a, b, json.loads(m.group(1))


def write_page(s, a, b, data):
    first = s[a:b].split('\n', 1)[0]
    block = first + '\nconst DATA = ' + json.dumps(data, separators=(',', ':'), sort_keys=True, ensure_ascii=False) + ';\n'
    open(SRC, 'w', encoding='utf-8').write(s[:a] + block + s[b:])


DASH_URL = 'https://claude.ai/artifact/J532xrrPfBJKFUzn2htdg8'
REDIRECT = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta http-equiv="refresh" content="0; url={DASH_URL}">
<title>NUTRA Dashboard</title>
<style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;font:15px system-ui,-apple-system,sans-serif;background:#fff;color:#111}}a{{color:#2563EB}}</style>
<script>location.replace({json.dumps(DASH_URL)});</script>
</head>
<body><p>Opening the NUTRA dashboard… <a href="{DASH_URL}">Open it</a></p></body>
</html>
'''


def build():
    """nutra.palmtreemedia.co (GitHub Pages) forwards to the live dashboard in Claude, where Settings can be saved."""
    open(OUT, 'w', encoding='utf-8').write(REDIRECT)


def num(v, kind, where):
    if v is None or v == '':
        return 0
    try:
        x = float(v)
    except (TypeError, ValueError):
        fail(f'{where}: {v!r} is not a number')
    if not math.isfinite(x):
        fail(f'{where}: {v!r} is not finite')
    return round(x, 2) if kind == 'money' else int(round(x))


def day(v):
    d = str(v or '')[:10]
    return d if DATE.match(d) else None


def merge_daily(cur, rows, since, today, where):
    """Replace days within [since, today] for one series dict {date: [spend, impr, clicks, lpv]}."""
    for d in [d for d in cur if since <= d <= today]:
        del cur[d]
    add_rows(cur, rows, since, today, where)


def add_rows(cur, rows, since, today, where):
    for r in rows:
        d = day(r.get('date'))
        if not d or not (since <= d <= today):
            fail(f'{where}: bad or out-of-range date {r.get("date")!r}')
        vals = [num(r.get('spend'), 'money', where), num(r.get('impr'), 'int', where),
                num(r.get('clicks'), 'int', where), num(r.get('lpv'), 'int', where)]
        if min(vals) < 0:
            fail(f'{where} {d}: negative value')
        if any(vals):
            old = cur.get(d)
            cur[d] = [round(old[0] + vals[0], 2), old[1] + vals[1], old[2] + vals[2], old[3] + vals[3]] if old else vals


RULE_METRICS = {  # metric: (label, direction, unit, denominator index in [spend, impr, clicks, lpv, checkouts, sales])
    'ctr': ('Link CTR', 'below', '%', None),
    'cpc': ('CPC', 'above', '$', 2),
    'cost_per_lpv': ('Cost per landing page view', 'above', '$', 3),
    'cost_per_checkout': ('Cost per checkout visit', 'above', '$', 4),
    'cost_per_sale': ('Cost per sale', 'above', '$', 5),
}
WINDOW_DAYS = {'today': 1, '3d': 3, '7d': 7}


def add_days(d, n):
    import datetime
    return (datetime.date.fromisoformat(d) + datetime.timedelta(days=n)).isoformat()


def rule_actions(p, data, today):
    """Pause rules from the NUTRA Settings page -> pause_ad / rule_alert / rule_blocked / rule_waiting actions."""
    rules = [r for r in (p.get('rules') or []) if r.get('enabled')]
    auto = p.get('automation') or {}
    if not rules or auto.get('enabled') is False:
        return []
    max_n = int(auto.get('maxPerRun') or 10)
    protect = auto.get('protectLast', True) is not False
    # recent log entries (rule id + ad id) so alerts/blocks aren't repeated every hour
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    seen = set()
    for x in p.get('ruleLog') or []:
        try:
            age_h = (now - datetime.datetime.fromisoformat(str(x.get('at')).replace('Z', '+00:00'))).total_seconds() / 3600
        except ValueError:
            continue
        if age_h < (24 if x.get('action') in ('alert', 'blocked', 'waiting') else 6):
            seen.add((x.get('ruleId'), x.get('adId')))
    # postback events matched to ads by utm_content = ad id (or ad name); unmatched counted per offer/day
    ad_conv, unmatched = {}, {}
    for r in p.get('jvzAds') or []:
        k, d, n = r.get('product_key'), day(r.get('day')), int(r.get('n') or 0)
        if not k or not d:
            continue
        idx = 4 if r.get('event') == 'initiated' else 5 if str(r.get('type') or 'SALE').upper() != 'RFND' else None
        if idx is None:
            continue
        ads = data['ads'].get(k, {})
        tag = str(r.get('utm_content') or '').strip()
        norm = lambda x: re.sub(r'[^a-z0-9]', '', str(x).lower())  # "C1 | Hand Callouts" == "c1_hand_callouts"
        aid = tag if tag in ads else next((a for a, ad in ads.items() if tag and norm(ad['n']) == norm(tag)), None)
        if aid:
            ad_conv.setdefault((k, aid), []).append((d, idx, n))
        else:
            unmatched.setdefault(k, []).append((d, idx, n))

    out, live = [], {}
    for o in data['offers']:
        k = o['key']
        if o['status'] != 'active':
            continue
        ads = data['ads'].get(k, {})
        live[k] = {aid for aid, ad in ads.items() if ad['s'] == 'ACTIVE'}
        start = data['settings'].get(k, {}).get('start') or today
        for r in rules:
            if r.get('offer') not in (None, '', 'all', k) or r.get('metric') not in RULE_METRICS:
                continue
            label, direction, unit, den = RULE_METRICS[r['metric']]
            thr = float(r.get('threshold') or 0)
            if thr <= 0:
                continue
            frm = start if r.get('window') == 'since_start' else add_days(today, 1 - WINDOW_DAYS.get(r.get('window'), 3))
            if r['metric'] in ('cost_per_checkout', 'cost_per_sale'):
                idx = 4 if r['metric'] == 'cost_per_checkout' else 5
                if any(frm <= d <= today and i == idx and n for d, i, n in unmatched.get(k, [])):
                    out.append({'action': 'rule_waiting', 'key': k, 'name': o['name'], 'acct': o['acct'], 'ruleId': r.get('id'),
                                'rule': rule_text(r), 'detail': f'{label}: some {"checkout visits" if idx == 4 else "sales"} could not be matched to an ad (add utm_content={{{{ad.id}}}} to ad URLs)'})
                    continue
            for aid in sorted(live[k]):
                ad = ads[aid]
                t = [0, 0, 0, 0, 0, 0]
                for d, v in ad['d'].items():
                    if frm <= d <= today:
                        for i in range(4):
                            t[i] += v[i]
                for d, i, n in ad_conv.get((k, aid), []):
                    if frm <= d <= today:
                        t[i] += n
                spend = round(t[0], 2)
                pb = float(r.get('protectBelowCpa') or 0)  # winner protection: never pause an ad selling at or under target
                if pb and t[5] > 0 and spend / t[5] <= pb:
                    continue
                if spend < float(r.get('minSpend') or 0) or t[1] < int(r.get('minImpr') or 0) or spend <= 0:
                    continue
                if r['metric'] == 'ctr':
                    if not t[1]:
                        continue
                    value = round(t[2] / t[1] * 100, 2)
                    hit = value < thr
                else:
                    value = round(spend / t[den], 2) if t[den] else None
                    hit = value > thr if value is not None else spend > thr
                if hit:
                    out.append({'action': 'pause_ad' if r.get('mode') != 'alert' else 'rule_alert', 'key': k, 'name': o['name'], 'acct': o['acct'],
                                'adId': aid, 'adName': ad['n'], 'campaign': ad['c'], 'ruleId': r.get('id'), 'rule': rule_text(r),
                                'metric': r['metric'], 'value': value, 'threshold': thr, 'spend': spend,
                                'detail': f'{label} {"none yet" if value is None else (f"{value}%" if unit == "%" else f"${value:,.2f}")} '
                                          f'(limit {f"{thr}%" if unit == "%" else f"${thr:,.2f}"}) on ${spend:,.2f} spend'})

    # one action per ad (first matching rule wins), skip ones already handled recently
    final, done = [], set()
    for a in out:
        if a['action'] == 'rule_waiting':
            if (a['ruleId'], None) not in seen and (a['ruleId'], a['key']) not in done:
                done.add((a['ruleId'], a['key']))
                final.append(a)
            continue
        if (a['key'], a['adId']) in done or (a['ruleId'], a['adId']) in seen:
            continue
        done.add((a['key'], a['adId']))
        final.append(a)
    # safety: never pause every live ad of an offer at once
    if protect:
        for k, ids in live.items():
            hits = {a['adId'] for a in final if a['action'] == 'pause_ad' and a['key'] == k}
            if ids and hits >= ids:
                for a in final:
                    if a['action'] == 'pause_ad' and a['key'] == k:
                        a['action'] = 'rule_blocked'
                        a['detail'] += ' · not paused: the rules would switch off every live ad of this offer'
    pauses = sorted([a for a in final if a['action'] == 'pause_ad'], key=lambda a: -a['spend'])
    for a in pauses[max_n:]:
        final.remove(a)
    return final


TH_DEFAULT = {'minCtr': 0.8, 'minCt': 8, 'minLpv': 200, 'coClicks': 75, 'coBench': 4}


def offer_funnel(data, k, frm, to):
    """Totals for one offer: spend, impr, link clicks, lpv, click-throughs (lander button clicks, or JVZoo
    order-form views on days before button counting started), checkout starts, sales."""
    btn_since = min([d for o in data.get('jvz', {}).values() for d, v in o.items() if len(v) > 4 and v[4]] or ['9999'])
    t = dict(spend=0, impr=0, clicks=0, lpv=0, through=0, starts=0, sales=0)
    for d, v in data['meta'].get(k, {}).items():
        if frm <= d <= to:
            t['spend'] += v[0]; t['impr'] += v[1]; t['clicks'] += v[2]; t['lpv'] += v[3]
    for d, v in data.get('jvz', {}).get(k, {}).items():
        if frm <= d <= to:
            t['starts'] += v[0]; t['sales'] += v[1]
            if d >= btn_since:
                t['through'] += v[4] if len(v) > 4 else 0
    for d, n in data.get('ofv', {}).get(k, {}).items():
        if frm <= d <= to and d < btn_since:
            t['through'] += n
    return t


def refresh_alerts(p, data, today):
    """'Time for new ads': an offer on the Do-it-for-me plan has too few live sales ads, or its live ads' CTR has decayed."""
    plan = (p.get('autoplan') or {}).get('offers') or {}
    out = []
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    for o in data['offers']:
        k, cfg = o['key'], plan.get(o['key'])
        if o['status'] != 'active' or not cfg or not cfg.get('enabled', True):
            continue
        recent = False
        for x in p.get('ruleLog') or []:
            if x.get('action') == 'refresh' and x.get('offer') == k:
                try:
                    recent = recent or (now - datetime.datetime.fromisoformat(str(x['at']).replace('Z', '+00:00'))).total_seconds() < 72 * 3600
                except (KeyError, ValueError):
                    pass
        if recent:
            continue
        frm3 = add_days(today, -2)
        live = [ad for ad in data['ads'].get(k, {}).values()
                if ad['s'] == 'ACTIVE' and re.search(r'sales|conver|purchase|\bconv\b', ad.get('c') or '', re.I)
                and any(frm3 <= d <= today and v[0] > 0 for d, v in ad['d'].items())]
        min_live = int(cfg.get('minLive') or 3)
        why = None
        if len(live) < min_live:
            why = f'only {len(live)} sales ad{"s" if len(live) != 1 else ""} still spending (target {min_live}+)'
        else:
            fi = fc = ri = rc = 0
            for ad in live:
                days = sorted(ad['d'])
                for d in days[:3]:
                    fi += ad['d'][d][1]; fc += ad['d'][d][2]
                for d in days[-3:]:
                    ri += ad['d'][d][1]; rc += ad['d'][d][2]
            decay = float(cfg.get('decay') or 30)
            if fi >= 2000 and ri >= 2000 and fc and (rc / ri) < (fc / fi) * (1 - decay / 100):
                why = f'live ads\' CTR fell from {fc / fi * 100:.2f}% to {rc / ri * 100:.2f}% (more than {decay:.0f}% down)'
        if why:
            out.append({'action': 'refresh_alert', 'key': k, 'name': o['name'], 'acct': o['acct'],
                        'detail': f'Time to upload new ads for {o["name"]}: {why}.'})
    return out


def checkout_warnings(p, data, today):
    """One alert per test when the ad and advertorial pass but enough people reached checkout with no sale."""
    th = {**TH_DEFAULT, **data.get('th', {})}
    out = []
    for o in data['offers']:
        k, st = o['key'], data['settings'].get(o['key'], {})
        if o['status'] != 'active':
            continue
        start = st.get('start') or today
        if any(x.get('action') == 'checkout' and x.get('offer') == k and str(x.get('at', ''))[:10] >= start for x in p.get('ruleLog') or []):
            continue
        t = offer_funnel(data, k, start, today)
        si = sc = 0  # CTR from sales campaigns only (awareness/engagement dilute it)
        for ad in data.get('ads', {}).get(k, {}).values():
            if re.search(r'sales|conver|purchase|\bconv\b', ad.get('c') or '', re.I):
                for d, v in ad['d'].items():
                    if start <= d <= today:
                        si += v[1]; sc += v[2]
        if si:
            t['impr'], t['clicks'] = si, sc
        ctr = t['clicks'] / t['impr'] * 100 if t['impr'] else 0
        ct = t['through'] / t['lpv'] * 100 if t['lpv'] else 0
        # enough people reached the order form → the ad and advertorial did their job; judge the checkout
        if t['sales'] == 0 and t['through'] >= th['coClicks'] and (t['impr'] < 2000 or ctr >= th['minCtr']):
            exp = t['through'] * th['coBench'] / 100
            out.append({'action': 'checkout_warning', 'key': k, 'name': o['name'], 'acct': o['acct'], 'spent': round(t['spend'], 2),
                        'through': t['through'], 'starts': t['starts'], 'expected': round(exp, 1),
                        'detail': f"{t['through']} people clicked through to the order form, {t['starts']} started checkout, 0 sales "
                                  f"(about {exp:.0f} expected at {th['coBench']}%) after ${t['spend']:,.0f} spend. "
                                  f"Your ad ({ctr:.2f}% CTR) and page are getting people to the order form; the checkout isn't closing."})
    return out


def rule_text(r):
    label, direction, unit, _ = RULE_METRICS.get(r.get('metric'), (r.get('metric'), 'above', '$', None))
    thr = r.get('threshold')
    return f'{label} {direction} {thr}%' if unit == '%' else f'{label} {direction} ${float(thr or 0):,.2f}'


def apply(p):
    s, a, b, data = read_page()
    for k in ('asOf', 'today', 'since'):
        if k not in p:
            fail(f'payload is missing "{k}"')
    today, since = p['today'], p['since']
    if not DATE.match(today) or not DATE.match(since) or since > today:
        fail('"today"/"since" must be YYYY-MM-DD with since <= today')
    if today < data.get('today', today):
        fail(f'payload today {today} is older than the page ({data["today"]}); refusing to go backwards')
    warn = []

    # Offers + their budget settings (NUTRA Tracker "products" table)
    if p.get('offers') is not None:
        offers, settings = [], {}
        for o in p['offers']:
            k = str(o.get('key') or '').strip()
            if not re.match(r'^[a-z0-9_-]{1,40}$', k):
                fail(f'offer key {k!r} is not a simple lowercase key')
            buy = o.get('buy_links') or []
            if isinstance(buy, str):
                buy = json.loads(buy or '[]')
            offers.append({'key': k, 'name': o.get('name') or k, 'offer': o.get('offer') or o.get('name') or k,
                           'network': o.get('network') or 'jvzoo', 'acct': str(o.get('ad_account_id') or ''),
                           'lander': o.get('lander_url') or '', 'buy': [{'label': x.get('label', ''), 'url': x.get('url', '')} for x in buy if isinstance(x, dict)],
                           'color': o.get('color') or '', 'status': o.get('status') or 'active', 'sort': num(o.get('sort'), 'int', 'offers.sort')})
            settings[k] = {'budget': num(o.get('budget'), 'money', f'{k}.budget'), 'start': day(o.get('start_date')) or since,
                           'warnAt': num(o.get('warn_at') or 70, 'int', f'{k}.warn_at'), 'autoPause': bool(o.get('auto_pause', True)),
                           'cps': None if o.get('commission_per_sale') in (None, '') else num(o['commission_per_sale'], 'money', f'{k}.cps'),
                           'autopausedAt': o.get('autopaused_at') or None,
                           '_warned': bool(o.get('warn_alerted_at')), '_depleted': bool(o.get('depleted_alerted_at'))}
        data['offers'], data['settings'] = offers, settings
    elif 'offers' not in data:
        fail('page has no offers yet and the payload has none')
    else:
        warn.append('Offer settings not refreshed this hour (kept previous)')
    keys = [o['key'] for o in data['offers']]

    if p.get('networks') is not None:
        data['networks'] = {str(n['key']): {'name': n.get('name') or n['key']} for n in p['networks'] if n.get('key')}
    if p.get('notes') is not None:
        data['notes'] = sorted([{'d': day(n.get('day')), 'p': n.get('product') or None, 't': str(n.get('text') or '')[:300]}
                                for n in p['notes'] if day(n.get('day'))], key=lambda n: n['d'])

    # Meta account-level daily numbers
    meta = p.get('meta') or {}
    data.setdefault('meta', {})
    for k in keys:
        rows = meta.get(k)
        if rows is None:
            if any(o['key'] == k and o['status'] == 'active' for o in data['offers']):
                warn.append(f'{k}: Meta data not refreshed this hour (kept previous numbers)')
            continue
        merge_daily(data['meta'].setdefault(k, {}), rows, since, today, f'meta.{k}')

    # Meta ad-level daily numbers (only the recent window is re-pulled each hour)
    ads_since = p.get('adsSince') or since
    data.setdefault('ads', {})
    for k, rows in (p.get('ads') or {}).items():
        if rows is None or k not in keys:
            continue
        cur = data['ads'].setdefault(k, {})
        for ad in cur.values():
            for d in [d for d in ad['d'] if ads_since <= d <= today]:
                del ad['d'][d]
        for r in rows:
            aid = str(r.get('id') or '')
            if not aid:
                continue
            ad = cur.setdefault(aid, {'n': '', 'c': '', 'a': '', 's': '', 'd': {}})
            ad['n'], ad['c'], ad['a'] = r.get('name') or ad['n'], r.get('campaign') or ad['c'], r.get('adset') or ad['a']
            ad['s'] = r.get('status') or ad['s']
            add_rows(ad['d'], [r], ads_since, today, f'ads.{k}.{aid}')
        for aid in [aid for aid, ad in cur.items() if not ad['d'] and ad['s'] in ('DELETED', 'ARCHIVED')]:
            del cur[aid]

    # Network postbacks (checkout visits, sales, refunds, commission) per offer and UTC day
    jv = p.get('jvz')
    if jv is None:
        warn.append('Network postbacks not refreshed this hour (kept previous numbers)')
    else:
        by_name = {o['offer'].lower().replace(' ', ''): o['key'] for o in data['offers']}
        new, skipped = {k: {} for k in keys}, 0
        for r in jv:
            key = r.get('product_key') or by_name.get(str(r.get('offer', '')).lower().replace(' ', ''))
            d = day(r.get('day'))
            if key not in new or not d:
                skipped += 1
                continue
            arr = new[key].setdefault(d, [0, 0, 0, 0, 0])
            n, c = num(r.get('n'), 'int', 'jvz.n'), num(r.get('commission'), 'money', 'jvz.commission')
            if r.get('event') == 'click':
                arr[4] += n
            elif r.get('event') == 'initiated':
                arr[0] += n
            elif r.get('event') == 'purchase':
                if str(r.get('type') or '').upper() == 'RFND':
                    arr[2] += n
                    arr[3] = round(arr[3] - abs(c), 2)
                else:
                    arr[1] += n
                    arr[3] = round(arr[3] + c, 2)
        data['jvz'] = new
        if skipped:
            print(f'note: skipped {skipped} postback row(s) not matched to an offer')

    # JVZoo order-form views (the AddToCart events JVZoo sends to each offer's pixel), per offer and day
    ofv_since = p.get('ofvSince') or since
    data.setdefault('ofv', {})
    for k, rows in (p.get('ofv') or {}).items():
        if rows is None or k not in keys:
            continue
        cur = data['ofv'].setdefault(k, {})
        for d in [d for d in cur if ofv_since <= d <= today]:
            del cur[d]
        for r in rows:
            d = day(r.get('date'))
            if d and ofv_since <= d <= today and num(r.get('n'), 'int', f'ofv.{k}') > 0:
                cur[d] = cur.get(d, 0) + num(r.get('n'), 'int', f'ofv.{k}')
    if p.get('thresholds') is not None:
        data['th'] = {**TH_DEFAULT, **{k: v for k, v in p['thresholds'].items() if k in TH_DEFAULT and isinstance(v, (int, float))}}

    data['asOf'], data['today'] = p['asOf'], today
    data['metaFrom'] = min(data.get('metaFrom', since), since)
    data['warn'] = warn

    # Budget alerts / auto-pause decisions
    actions = []
    for o in data['offers']:
        k, st = o['key'], data['settings'].get(o['key'], {})
        if o['status'] != 'active' or not st.get('budget') or p.get('offers') is None:  # no fresh alert state → no budget actions
            continue
        spent = round(sum(v[0] for d, v in data['meta'].get(k, {}).items() if st['start'] <= d <= today), 2)
        pct = spent / st['budget'] * 100
        base = {'key': k, 'name': o['name'], 'acct': o['acct'], 'spent': spent, 'budget': st['budget'], 'pct': round(pct, 1)}
        if pct >= 100 and st['autoPause'] and not st['autopausedAt']:
            actions.append({**base, 'action': 'pause'})
        if pct >= 100 and not st['_depleted']:
            actions.append({**base, 'action': 'alert_depleted'})
        elif pct >= st['warnAt'] and not st['_warned'] and pct < 100:
            actions.append({**base, 'action': 'alert_warning', 'warnAt': st['warnAt']})
    actions += rule_actions(p, data, today)
    actions += checkout_warnings(p, data, today)
    actions += refresh_alerts(p, data, today)
    for st in data['settings'].values():
        st.pop('_warned', None), st.pop('_depleted', None)
    write_page(s, a, b, data)
    build()
    json.dump(actions, open(ACT, 'w'), indent=1)

    print(f'updated: asOf={data["asOf"]} today={today} offers={len(keys)} warnings={len(warn)}')
    month = today[:8] + '01'
    for o in data['offers']:
        k = o['key']
        m = data['meta'].get(k, {})
        print(f'  {o["name"][:26]:26} {o["status"]:8} month spend ${sum(v[0] for d, v in m.items() if d >= month):,.2f}'
              f' · ads {len(data["ads"].get(k, {}))} · checkouts {sum(v[0] for v in data["jvz"].get(k, {}).values())}'
              f' · sales {sum(v[1] for v in data["jvz"].get(k, {}).values())}')
    for w in warn:
        print('  WARNING:', w)
    print('actions:', json.dumps(actions) if actions else 'none')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        fail(__doc__)
    if sys.argv[1] == '--build':
        read_page()
        build()
        print('built index.html')
    else:
        apply(json.load(open(sys.argv[1], encoding='utf-8')))
