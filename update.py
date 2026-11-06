#!/usr/bin/env python3
"""Refresh the numbers in dashboard.html and rebuild index.html.

    python3 update.py payload.json   # merge fresh Meta + JVZoo numbers, then build
    python3 update.py --build        # only rebuild index.html from dashboard.html

dashboard.html is the source (it is also what gets published to the claude.ai artifact).
index.html is the GitHub Pages copy (dashboard.html wrapped in a full HTML document).
Only the block between "// @@DATA_START" and "// @@DATA_END" is ever rewritten.
See README.md for the payload format.
"""
import json, re, sys, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
SRC, OUT = os.path.join(HERE, 'dashboard.html'), os.path.join(HERE, 'index.html')
KEYS = ['wellness', 'neuro', 'glp']
NAMES = {'wellness': 'Wellness Notes (Synaptril)', 'neuro': 'NeuroSharp', 'glp': 'Glpatches'}
OFFER_TO_KEY = {'synaptril': 'wellness', 'neurosharp': 'neuro', 'glpatches': 'glp'}
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
    block = first + '\nconst DATA = ' + json.dumps(data, separators=(',', ':'), sort_keys=True) + ';\n'
    open(SRC, 'w', encoding='utf-8').write(s[:a] + block + s[b:])


def build():
    s = open(SRC, encoding='utf-8').read()
    i = s.index('</style>') + len('</style>')
    open(OUT, 'w', encoding='utf-8').write(HEAD + s[:i] + '\n</head>\n<body>\n' + s[i:] + '\n</body>\n</html>\n')


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


def apply(payload):
    s, a, b, data = read_page()
    for k in ('asOf', 'today', 'since'):
        if k not in payload:
            fail(f'payload is missing "{k}"')
    today, since = payload['today'], payload['since']
    if not DATE.match(today) or not DATE.match(since) or since > today:
        fail('"today"/"since" must be YYYY-MM-DD with since <= today')
    if today < data.get('today', today):
        fail(f'payload today {today} is older than the page ({data["today"]}); refusing to go backwards')

    warn = []
    meta = payload.get('meta') or {}
    for k in KEYS:
        rows = meta.get(k)
        if rows is None:
            warn.append(f'{NAMES[k]}: Meta data not refreshed this hour (kept previous numbers)')
            continue
        cur = data['meta'].setdefault(k, {})
        for d in [d for d in cur if since <= d <= today]:
            del cur[d]
        for r in rows:
            d = r.get('date')
            if not d or not DATE.match(d) or not (since <= d <= today):
                fail(f'meta.{k}: bad or out-of-range date {d!r}')
            vals = [num(r.get('spend'), 'money', f'meta.{k}.{d}.spend'), num(r.get('impr'), 'int', f'meta.{k}.{d}.impr'),
                    num(r.get('clicks'), 'int', f'meta.{k}.{d}.clicks'), num(r.get('lpv'), 'int', f'meta.{k}.{d}.lpv')]
            if min(vals) < 0:
                fail(f'meta.{k}.{d}: negative value')
            if any(vals):
                cur[d] = vals

    jv = payload.get('jvz')
    if jv is None:
        warn.append('JVZoo: tracker not refreshed this hour (kept previous numbers)')
    else:
        new, skipped = {k: {} for k in KEYS}, 0
        for r in jv:
            key = OFFER_TO_KEY.get(str(r.get('offer', '')).lower().replace(' ', ''))
            d = str(r.get('day', ''))[:10]
            if not key or not DATE.match(d):
                skipped += 1
                continue
            arr = new[key].setdefault(d, [0, 0, 0, 0])
            n = num(r.get('n'), 'int', 'jvz.n')
            c = num(r.get('commission'), 'money', 'jvz.commission')
            if r.get('event') == 'initiated':
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
            print(f'note: skipped {skipped} JVZoo row(s) for other/unknown offers')

    data['asOf'] = payload['asOf']
    data['today'] = today
    data['metaFrom'] = min(data.get('metaFrom', since), since)
    data['warn'] = warn
    write_page(s, a, b, data)
    build()

    print(f'updated: asOf={data["asOf"]} today={today} warnings={len(warn)}')
    month = today[:8] + '01'
    for k in KEYS:
        m = data['meta'].get(k, {})
        sp = sum(v[0] for d, v in m.items() if d >= month)
        cl = sum(v[2] for d, v in m.items() if d >= month)
        j = data['jvz'].get(k, {})
        print(f'  {NAMES[k]:28} this month: spend ${sp:,.2f}, clicks {cl}, '
              f'checkouts {sum(v[0] for v in j.values())}, sales {sum(v[1] for v in j.values())} (all time)')
    for w in warn:
        print('  WARNING:', w)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        fail(__doc__)
    if sys.argv[1] == '--build':
        read_page()
        build()
        print('built index.html')
    else:
        apply(json.load(open(sys.argv[1], encoding='utf-8')))
