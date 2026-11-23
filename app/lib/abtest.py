"""Copy A/B tests for built pages. Claude writes version B (one element changed), the same /p/<slug> link splits
visitors 50/50 (sticky cookie), and views / bundle clicks / checkouts / sales are counted per version.
Sales are matched through the JVZoo tid: the page appends "~<test id><A|B>" to it, the postback handler strips it
off into events.variant (so ad-level tracking keeps working)."""
import datetime, json, math, re, secrets
from . import db, agent, notify

SCHEMA = """
create table if not exists ab_stats (page_id text not null, code text not null, views int not null default 0,
  primary key (page_id, code));
alter table events add column if not exists variant text;
alter table pages add column if not exists test jsonb;
alter table pages add column if not exists tests_done jsonb not null default '[]';
"""
FOCUS = {'angle': 'the angle and headline: a different main mistake/hook, a new h1 and sub (and the intro lines that set it up)',
         'intro': 'the opening only: the paragraphs right under the headline/photo (problem-first, a "BUT:" twist, or a short checklist), keep the headline',
         'offer': 'how the offer is framed: the buy-box line, the cta block, the "easy way" shortcut line and button wording (e.g. lead with days of supply or the guarantee instead of cost per day)',
         'hormozi': ('the OFFER part only, in Alex Hormozi style (the article sections stay exactly as they are): the buy-box line, the '
                     'cta block, the "easy way" section and its shortcut line, and button wording. Use: (1) plain value math with the REAL '
                     'cost per day vs. an everyday thing the reader already pays for (e.g. "less than the afternoon snack it replaces"); '
                     '(2) the whole package spelled out (packs, days of supply, one order, no subscription if the checkout is one-time); '
                     '(3) risk reversal using ONLY the real return policy and days, credited to the vendor; (4) make the choice easy: '
                     'say which bundle is the obvious pick and show the math. One line of light edge is fine ("the 6-pack math is almost '
                     'unfair"). Never: "should be illegal", "insane", hype, fake scarcity or deadlines, invented bonuses or discounts, '
                     'guarantees the vendor does not give, or any health/weight promise. Short, punchy, plain words.'),
         'length': 'a shorter page: tighten every section, drop the weakest block, keep all figures, facts, offer and FAQ essentials'}
FOCUS_LABEL = {'angle': 'Angle & headline', 'intro': 'Opening', 'offer': 'Offer framing', 'hormozi': 'Hormozi-style offer', 'length': 'Shorter page'}
MIN_DAYS, MIN_VIEWS, SURE = 7, 500, 0.95
CODE_RE = re.compile(r'^[0-9a-f]{4}[AB]$')
TID_RE = re.compile(r'^(.*)~([0-9a-f]{4}[AB])$')


_ready = False


def setup():
    global _ready
    if not _ready:
        db.conn().execute(SCHEMA)
        _ready = True


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(d=None):
    return (d or now()).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_tid(v):
    """'1202…~ab12B' -> ('1202…', 'ab12B'); anything else -> (v, None)."""
    m = TID_RE.match(str(v or ''))
    return (m.group(1) or None, m.group(2)) if m else (v, None)


# ── making version B ──
def request_variant(row, focus, note, user, base, tok, tok_hash):
    setup()
    if focus not in FOCUS:
        return {'ok': False, 'error': 'Pick what to test'}
    tid = secrets.token_hex(2)
    test = {'id': tid, 'state': 'building', 'focus': focus, 'note': str(note or '')[:500], 'by': user['email'], 'created_at': iso(),
            'auto': True}
    msg = (f"VARIANT: write version B of this page's copy for an A/B test. Page type: {'INFO (kind=info, INFO schema)' if row.get('kind') == 'info' else 'STORY advertorial'}.\n"
           f"Change ONLY {FOCUS[focus]}. Keep everything else exactly as it is: facts, prices, bundles and their URLs, product, ingredients,"
           f" figures, images, compliance text and the design. Make the change bold enough to matter (a real alternative, not a reworded copy).\n"
           + (f"Team note: {test['note']}\n" if test['note'] else '') +
           f"GET $BASE/api/agent/$PAGE/content (that is version A), then POST the FULL content JSON of version B to "
           f"$BASE/api/agent/$PAGE/variant (same auth). Fix any problems it reports and POST again. Do NOT post to /content. "
           f"Then reply with 1-2 plain lines: what B changes and why it could win.\n\nPAGE={row['id']}\nBASE={base}\nPAGE_TOKEN={tok}")
    try:
        alive = False
        if row.get('session_id'):
            try:
                alive = (agent.session(row['session_id']).get('status') or '') in ('idle', 'running')
            except Exception:
                alive = False
        if alive:
            agent.send(row['session_id'], msg)
            test['session_id'] = row['session_id']
        else:
            from . import pages
            s = agent.start_session(pages.system_prompt(), f"variant: {row.get('name') or row['slug']}", msg, row['id'])
            test['session_id'] = s.get('id')
    except Exception as e:
        return {'ok': False, 'error': f'Claude could not start: {str(e)[:200]}'}
    db.q('update pages set test = %s, token_hash = %s, updated_at = now() where id = %s', (db.J(test), tok_hash, row['id']))
    return {'ok': True}


def deliver_variant(row, content, validate):
    t = row.get('test') or {}
    if t.get('state') not in ('building', 'ready'):
        return {'ok': False, 'problems': ['no variant was requested for this page']}
    probs = validate(content)
    a_urls = sorted(str(b.get('url')) for b in ((row.get('content') or {}).get('offer') or {}).get('bundles') or [])
    b_urls = sorted(str(b.get('url')) for b in (content.get('offer') or {}).get('bundles') or [])
    if a_urls != b_urls:
        probs.append('keep offer.bundles and their URLs exactly as in version A')
    low = json.dumps(content).lower()
    for bad in ('illegal', 'insane', 'only today', 'limited time', 'selling out', 'free bonus'):
        if bad in low:
            probs.append(f'remove "{bad}": hype or scarcity the checkout does not show gets ad accounts flagged')
    if probs:
        return {'ok': False, 'problems': probs}
    t.update({'state': 'ready', 'b': content, 'ready_at': iso()})
    db.q('update pages set test = %s, updated_at = now() where id = %s', (db.J(t), row['id']))
    return {'ok': True, 'note': 'Version B saved. Reply with your 1-2 line summary.'}


def check_building(row):
    """While B is being written: notice when Claude stopped without delivering."""
    t = row.get('test') or {}
    if t.get('state') != 'building' or not t.get('session_id'):
        return row
    try:
        created = datetime.datetime.fromisoformat(t['created_at'].replace('Z', '+00:00'))
        st = agent.session(t['session_id']).get('status') or ''
    except Exception:
        return row
    age = (now() - created).total_seconds()
    if (st in ('idle', 'terminated') and age > 120) or age > 45 * 60:
        t.update({'state': 'failed', 'error': (agent.last_words(t['session_id']) or 'Claude stopped before writing version B.')[:400]})
        db.q('update pages set test = %s, updated_at = now() where id = %s', (db.J(t), row['id']))
        row = {**row, 'test': t}
    return row


# ── running ──
def start(row, auto):
    t = row.get('test') or {}
    if t.get('state') != 'ready':
        return {'ok': False, 'error': 'Version B is not ready yet'}
    if not row.get('published'):
        return {'ok': False, 'error': 'Publish the page first, then start the test'}
    t.update({'state': 'running', 'started_at': iso(), 'auto': bool(auto)})
    db.q('update pages set test = %s, updated_at = now() where id = %s', (db.J(t), row['id']))
    return {'ok': True}


def set_auto(row, auto):
    t = row.get('test') or {}
    t['auto'] = bool(auto)
    db.q('update pages set test = %s, updated_at = now() where id = %s', (db.J(t), row['id']))
    return {'ok': True}


def discard(row):
    t = row.get('test') or {}
    if t.get('session_id') and t.get('state') == 'building':
        try:
            agent.stop(t['session_id'])
        except Exception:
            pass
    db.q('update pages set test = null, updated_at = now() where id = %s', (row['id'],))
    return {'ok': True}


def results(row):
    t = row.get('test') or {}
    if t.get('state') not in ('running',) or not t.get('id'):
        return None
    out = {}
    for v in 'AB':
        code = t['id'] + v
        views = (db.q1('select views from ab_stats where page_id = %s and code = %s', (row['id'], code)) or {}).get('views') or 0
        ev = db.q("""select event, coalesce(transaction_type,'') as typ, count(*)::int as n, coalesce(sum(commission),0)::float as c
                     from events where variant = %s and not is_test group by 1,2""", (code,))
        g = lambda e: sum(r['n'] for r in ev if r['event'] == e and r['typ'].upper() != 'RFND')
        rev = sum(r['c'] for r in ev if r['event'] == 'purchase' and r['typ'].upper() != 'RFND') - \
            sum(abs(r['c']) for r in ev if r['event'] == 'purchase' and r['typ'].upper() == 'RFND')
        out[v] = {'views': views, 'clicks': g('click'), 'checkouts': g('initiated'), 'sales': g('purchase'), 'revenue': round(rev, 2)}
        out[v]['click_rate'] = out[v]['clicks'] / views if views else 0
        out[v]['rpv'] = out[v]['revenue'] / views if views else 0
    a, b = out['A'], out['B']
    metric = 'sales' if min(a['sales'], b['sales']) >= 10 else 'clicks'
    pa, pb = (a[metric] / a['views'] if a['views'] else 0), (b[metric] / b['views'] if b['views'] else 0)
    prob = None
    if a['views'] >= 50 and b['views'] >= 50:
        se = math.sqrt(max(pa * (1 - pa), 1e-9) / a['views'] + max(pb * (1 - pb), 1e-9) / b['views'])
        prob = 0.5 * (1 + math.erf(((pb - pa) / se) / math.sqrt(2))) if se else 0.5
    started = datetime.datetime.fromisoformat(t['started_at'].replace('Z', '+00:00'))
    days = (now() - started).total_seconds() / 86400
    lead = None if prob is None else ('B' if prob >= 0.5 else 'A')
    sure = None if prob is None else max(prob, 1 - prob)
    ready = days >= MIN_DAYS and min(a['views'], b['views']) >= MIN_VIEWS
    if prob is None:
        verdict = 'Not enough visitors yet (needs 50 per version for a first read).'
    elif ready and sure >= SURE:
        verdict = f'{lead} wins: {sure * 100:.0f}% sure, on {metric} per visitor.'
    else:
        need = []
        if days < MIN_DAYS:
            need.append(f'{math.ceil(MIN_DAYS - days)} more day(s)')
        if min(a['views'], b['views']) < MIN_VIEWS:
            need.append(f'{MIN_VIEWS} visitors per version')
        verdict = f'{lead} is ahead, {sure * 100:.0f}% sure on {metric} per visitor.' + (f' Keep going: needs {" and ".join(need)}.' if need else ' Not sure enough yet.')
    return {'A': a, 'B': b, 'metric': metric, 'prob_b': prob, 'leader': lead, 'sure': sure, 'days': round(days, 1),
            'ready': ready, 'verdict': verdict, 'decided': bool(ready and sure and sure >= SURE)}


def pick(row, winner, how='manual', res=None):
    t = row.get('test') or {}
    if winner not in ('A', 'B') or t.get('state') not in ('running', 'ready'):
        return {'ok': False, 'error': 'No test to finish'}
    res = res if res is not None else results(row)
    rec = {'id': t.get('id'), 'focus': t.get('focus'), 'focus_label': FOCUS_LABEL.get(t.get('focus'), t.get('focus')), 'note': t.get('note'),
           'started_at': t.get('started_at'), 'ended_at': iso(), 'winner': winner, 'how': how,
           'results': {k: v for k, v in (res or {}).items() if k in ('A', 'B', 'metric', 'sure', 'days', 'verdict')}}
    done = (row.get('tests_done') or []) + [rec]
    if winner == 'B':
        db.q('update pages set content = %s, test = null, tests_done = %s, updated_at = now() where id = %s', (db.J(t['b']), db.J(done), row['id']))
    else:
        db.q('update pages set test = null, tests_done = %s, updated_at = now() where id = %s', (db.J(done), row['id']))
    return {'ok': True, 'winner': winner}


def auto_check_all():
    """Hourly: finish running tests whose winner is clear (if the page allows auto)."""
    setup()
    msgs = []
    for row in db.q("select * from pages where test->>'state' = 'running'"):
        t = row['test']
        if not t.get('auto'):
            continue
        res = results(row)
        if res and res['decided']:
            pick(row, res['leader'], 'auto', res)
            msgs.append(f"{row.get('name') or row['slug']}: A/B test finished. Version {res['leader']} won ({res['sure'] * 100:.0f}% sure on "
                        f"{res['metric']} per visitor). It now gets 100% of visitors.")
    if msgs:
        try:
            notify.send('\n\n'.join(msgs), subject='NUTRA: A/B test winner')
        except Exception:
            pass
    return msgs


def public(row):
    t = row.get('test')
    out = None
    if t:
        out = {k: t.get(k) for k in ('id', 'state', 'focus', 'note', 'by', 'created_at', 'ready_at', 'started_at', 'auto', 'error')}
        out['focus_label'] = FOCUS_LABEL.get(t.get('focus'), t.get('focus'))
        if t.get('state') == 'running':
            try:
                out['results'] = results(row)
            except Exception:
                out['results'] = None
    return {'test': out, 'tests_done': row.get('tests_done') or []}


# ── serving ──
def choose(row, cookie_val, forced):
    """-> (content, code or None, set_cookie or None)"""
    t = row.get('test') or {}
    if forced in ('A', 'B') and t.get('b'):
        return (t['b'] if forced == 'B' else row['content']), None, None
    if t.get('state') != 'running' or not t.get('b') or not row.get('published'):
        return row['content'], None, None
    v = cookie_val if cookie_val in ('A', 'B') else ('A' if secrets.randbelow(2) == 0 else 'B')
    return (t['b'] if v == 'B' else row['content']), t['id'] + v, (None if cookie_val == v else v)


def count_view(page_id, code):
    if not CODE_RE.match(code or ''):
        return
    setup()
    db.q("""insert into ab_stats (page_id, code, views) values (%s, %s, 1)
            on conflict (page_id, code) do update set views = ab_stats.views + 1""", (page_id, code))


AB_JS = r"""<script>(function(){var c=__CODE__;window.__AB=c;
document.querySelectorAll('a[data-bundle]').forEach(function(l){try{var x=new URL(l.href),t=x.searchParams.get('tid')||'';x.searchParams.set('tid',t.replace(/~[0-9a-f]{4}[AB]$/,'')+'~'+c);l.href=x.toString();}catch(e){}});
try{navigator.sendBeacon('/api/public/page-view',JSON.stringify({page:__PAGE__,v:c}));}catch(e){}})();</script>"""
