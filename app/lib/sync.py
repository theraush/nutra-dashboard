"""The hourly job: Meta numbers + postbacks -> dashboard data, then budget pauses, pause rules and alerts.
Meta is only ever asked to PAUSE things."""
import datetime, re, traceback
from . import db, engine, meta, notify

KEY_RE = re.compile(r'^[a-z0-9_-]{1,40}$')


def _iso(dt=None):
    return (dt or datetime.datetime.now(datetime.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')


def _docs(prefix):
    return [{'id': r['path'].split('/', 1)[1], **r['data']} for r in db.kv_list(prefix)]


def apply_offer_edits(errors):
    """Settings → Offers & budgets saves to kv offers/<key>; copy into the offers table. A new budget re-arms alerts."""
    for e in _docs('offers'):
        k = e['id']
        if not KEY_RE.match(k):
            continue
        sets, args = [], []
        if 'budget' in e:
            b = e['budget'] if isinstance(e['budget'], (int, float)) else 0
            sets += ["warn_alerted_at = case when budget is distinct from %s then null else warn_alerted_at end",
                     "depleted_alerted_at = case when budget is distinct from %s then null else depleted_alerted_at end",
                     "autopaused_at = case when budget is distinct from %s then null else autopaused_at end", 'budget = %s']
            args += [b, b, b, b]
        if 'cps' in e:
            sets.append('commission_per_sale = %s'); args.append(e['cps'] if isinstance(e['cps'], (int, float)) else None)
        if e.get('start') and re.match(r'^\d{4}-\d{2}-\d{2}$', str(e['start'])):
            sets.append('start_date = %s'); args.append(e['start'])
        if isinstance(e.get('warnAt'), (int, float)):
            sets.append('warn_at = %s'); args.append(int(min(99, max(10, e['warnAt']))))
        if isinstance(e.get('autoPause'), bool):
            sets.append('auto_pause = %s'); args.append(e['autoPause'])
        if sets:
            try:
                db.q(f"update offers set {', '.join(sets)} where key = %s", args + [k])
            except Exception as ex:
                errors.append(f'offer {k}: {ex}')


def run(force=False):
    now = datetime.datetime.now(datetime.timezone.utc)
    errors, done = [], []
    lock = db.q1('select pg_try_advisory_lock(424242) as ok')
    if not lock['ok']:
        return {'ok': False, 'error': 'another sync is running'}
    try:
        return _run(now, errors, done)
    except Exception as ex:
        errors.append(f'{type(ex).__name__}: {ex}')
        _status(now, errors, False, 0, '')
        return {'ok': False, 'error': str(ex), 'trace': traceback.format_exc()[-1500:]}
    finally:
        db.q('select pg_advisory_unlock(424242)')


def _run(now, errors, done):
    today = now.date().isoformat()
    first = now.date().replace(day=1)
    since = (first - datetime.timedelta(days=1)).replace(day=1).isoformat()  # first day of the previous month
    snap = db.q1('select data from snapshot where id = 1')
    prev = snap['data'] if snap else {}
    ads_since = (now.date() - datetime.timedelta(days=6)).isoformat() if prev.get('ads') else since
    ofv_since = (now.date() - datetime.timedelta(days=13)).isoformat()

    rules = _docs('rules')
    automation = db.kv_data('config/automation', {})
    thresholds = db.kv_data('config/thresholds')
    autoplan = db.kv_data('config/autoplan')
    log_row = db.kv_get('log/recent')
    log = (log_row['data'].get('items') if log_row else None) or []

    apply_offer_edits(errors)
    offers = db.q("""select key,name,offer,network,ad_account_id,pixel_id,lander_url,buy_links,color,status,sort,budget,
                     start_date::text as start_date,warn_at,auto_pause,commission_per_sale,autopaused_at,warn_alerted_at,depleted_alerted_at
                     from offers order by sort, created_at""")
    for o in offers:
        for f in ('budget', 'commission_per_sale'):
            o[f] = float(o[f]) if o[f] is not None else None
        for f in ('autopaused_at', 'warn_alerted_at', 'depleted_alerted_at'):
            o[f] = _iso(o[f]) if o[f] else None
    notes = db.q('select day::text as day, product, text from notes order by day') + [
        {'day': n.get('day'), 'product': n.get('product'), 'text': n.get('text')} for n in _docs('notes') if n.get('day') and n.get('text')]
    jvz = db.q("""select product_key, offer, to_char((received_at at time zone 'UTC')::date,'YYYY-MM-DD') as day, event,
                  transaction_type as type, count(*)::int as n, coalesce(sum(commission),0)::float as commission
                  from events where not is_test group by 1,2,3,4,5 order by 3""")
    jvz_ads = db.q("""select product_key, to_char((received_at at time zone 'UTC')::date,'YYYY-MM-DD') as day, event,
                      transaction_type as type, utm_content, count(*)::int as n from events
                      where not is_test and received_at > now() - interval '45 days' group by 1,2,3,4,5""")
    networks = [{'key': n['id'], 'name': n.get('name') or n['id']} for n in _docs('networks')] or None

    m_acct, m_ads, ofv, latest = {}, {}, {}, None
    for o in offers:
        if o['status'] == 'archived' or not o['ad_account_id']:
            continue
        k = o['key']
        try:
            m_acct[k] = meta.account_daily(o['ad_account_id'], since, today)
            latest = max([latest or ''] + [r['date'] for r in m_acct[k]]) or None
        except meta.MetaError as ex:
            m_acct[k] = None; errors.append(f'{k} Meta: {ex}')
        try:
            m_ads[k] = meta.ads_daily(o['ad_account_id'], ads_since, today)
        except meta.MetaError as ex:
            m_ads[k] = None; errors.append(f'{k} Meta ads: {ex}')
        try:
            px = o['pixel_id'] or meta.first_pixel(o['ad_account_id'])
            ofv[k] = meta.add_to_cart_daily(px, ofv_since) if px else None
        except meta.MetaError:
            ofv[k] = None

    p = {'asOf': _iso(now), 'today': latest or today, 'since': since, 'adsSince': ads_since, 'ofvSince': ofv_since,
         'offers': offers, 'networks': networks, 'notes': notes, 'meta': m_acct, 'ads': m_ads, 'ofv': ofv,
         'jvz': jvz, 'jvzAds': jvz_ads, 'rules': rules, 'automation': automation, 'thresholds': thresholds,
         'autoplan': autoplan, 'ruleLog': log}
    if p['today'] < prev.get('today', p['today']):
        p['today'] = prev['today']
    data, actions, warn = engine.compute(p, prev)
    first_ev = db.q1("select to_char(min(received_at) at time zone 'UTC','YYYY-MM-DD') as d from events where not is_test")
    data['jvzSince'] = min([x for x in (prev.get('jvzSince'), first_ev and first_ev['d']) if x] or [p['today']])

    # ── act ──
    new_log, push, paused_ads = [], [], 0
    by_key = {o['key']: o for o in offers}

    def logitem(a, action, **kw):
        new_log.append({'at': _iso(), 'offer': a.get('key'), 'adId': a.get('adId'), 'adName': a.get('adName'), 'ruleId': a.get('ruleId'),
                        'rule': a.get('rule'), 'metric': a.get('metric'), 'value': a.get('value'), 'spend': a.get('spend', a.get('spent')),
                        'action': action, 'detail': a.get('detail'), **kw})

    budget_msgs, pause_msgs, other_msgs = [], [], []
    paused_offer = set()
    for a in actions:
        k, kind = a['key'], a['action']
        if kind == 'pause':
            names = []
            try:
                for c in meta.active_campaigns(a['acct']):
                    meta.pause(c['id']); names.append(c['name'])
                db.q('update offers set autopaused_at = now() where key = %s', (k,))
                db.q('insert into budget_events (product, event, detail, amount) values (%s,%s,%s,%s)',
                     (k, 'auto_paused', f"Paused {len(names)} campaign(s): {', '.join(names) or 'none active'} at ${a['spent']:,.2f} of ${a['budget']:,.0f}", a['spent']))
                data['settings'][k]['autopausedAt'] = _iso()
                paused_offer.add(k)
                done.append(f"paused {a['name']} campaigns: {', '.join(names) or 'none active'}")
            except meta.MetaError as ex:
                errors.append(f"{k} budget pause: {ex}")
        elif kind in ('alert_depleted', 'alert_warning'):
            if kind == 'alert_depleted':
                msg = f"{a['name']}: test budget used up: ${a['spent']:,.2f} of ${a['budget']:,.0f}" + (', campaigns paused' if k in paused_offer else '')
                col = 'depleted_alerted_at'
            else:
                msg = f"{a['name']}: {a['pct']:.0f}% of ${a['budget']:,.0f} test budget spent (${a['spent']:,.2f})"
                col = 'warn_alerted_at'
            db.q(f'update offers set {col} = now() where key = %s', (k,))
            db.q('insert into budget_events (product, event, detail, amount) values (%s,%s,%s,%s)', (k, kind, msg, a['spent']))
            budget_msgs.append(msg); done.append(kind)
        elif kind == 'checkout_warning':
            budget_msgs.insert(0, f"⚠️ {a['name']}: checkout problem. {a['detail']} Consider stopping it or asking the vendor.")
            logitem({**a, 'adName': 'Whole offer', 'rule': 'Offer check', 'value': None}, 'checkout')
        elif kind == 'refresh_alert':
            other_msgs.append(a['detail'])
            logitem({**a, 'adName': 'Whole offer', 'rule': 'Do it for me', 'value': None}, 'refresh')
        elif kind == 'pause_ad':
            try:
                meta.pause(a['adId'])
                logitem(a, 'paused'); paused_ads += 1
                pause_msgs.append(f"{a['adName']} ({a['detail']})")
                ad = data['ads'].get(k, {}).get(a['adId'])
                if ad:
                    ad['s'] = 'PAUSED'
            except meta.MetaError as ex:
                logitem(a, 'failed'); errors.append(f"pause {a['adName']}: {ex}")
        elif kind == 'rule_alert':
            logitem(a, 'alert'); other_msgs.append(f"{a['name']} · {a['adName']}: {a['detail']}")
        elif kind == 'rule_blocked':
            logitem(a, 'blocked'); other_msgs.append(f"{a['name']}: {a['detail']}")
        elif kind == 'rule_waiting':
            logitem(a, 'waiting')

    msgs = budget_msgs + ([f"Paused {len(pause_msgs)} ad{'s' if len(pause_msgs) != 1 else ''}: " + '; '.join(pause_msgs)] if pause_msgs else []) + other_msgs
    if msgs:
        errors += notify.send('\n\n'.join(msgs), subject='NUTRA: ' + msgs[0][:80])

    if new_log:
        items = (new_log + log)[:100]
        r = db.kv_set('log/recent', {'items': items}, log_row['version'] if log_row else None)
        if r is None:  # changed meanwhile: merge with the latest
            cur = db.kv_data('log/recent', {}) or {}
            db.kv_set('log/recent', {'items': (new_log + (cur.get('items') or []))[:100]})

    data['warn'] = (data.get('warn') or []) + [e for e in errors][:5]
    db.q("""insert into snapshot (id, data, at) values (1, %s, now())
            on conflict (id) do update set data = excluded.data, at = now()""", (db.J(data),))

    summary = ' · '.join(
        f"{o['name']} ${sum(v[0] for d, v in data['meta'].get(o['key'], {}).items() if d >= data['settings'][o['key']]['start']):,.2f}/${data['settings'][o['key']]['budget']:,.0f}"
        for o in data['offers'] if o['status'] == 'active')
    _status(now, errors, True, paused_ads, summary)
    return {'ok': not errors, 'errors': errors, 'actions': [a['action'] for a in actions], 'done': done, 'summary': summary}


def _status(now, errors, published, paused, summary):
    db.kv_set('config/sync', {'at': _iso(now), 'ok': not errors, 'published': published, 'pushed': True, 'paused': paused,
                              'summary': summary, 'error': '; '.join(errors)[:400]})
