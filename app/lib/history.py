"""Archive a tested product: pause its live Meta campaigns, hide it from Overview, and keep a frozen summary
in kv history/<key> for the History tab. Restore brings it back (it never restarts ads: Meta is only ever paused)."""
import datetime
from . import db, meta


def _iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _snap():
    r = db.q1('select data from snapshot where id = 1')
    return r['data'] if r else {}


def _set_status_in_snapshot(key, status):
    """So the dashboard hides/shows the product right away, not only after the next hourly sync."""
    db.q("""update snapshot set data = jsonb_set(data, '{offers}', (
              select coalesce(jsonb_agg(case when o->>'key' = %s then jsonb_set(o, '{status}', to_jsonb(%s::text)) else o end), '[]'::jsonb)
              from jsonb_array_elements(data->'offers') o)) where id = 1 and data ? 'offers'""", (key, status))


def summary(key, snap):
    m = (snap.get('meta') or {}).get(key) or {}
    j = (snap.get('jvz') or {}).get(key) or {}
    st = (snap.get('settings') or {}).get(key) or {}
    spend_days = sorted(d for d, v in m.items() if v and float(v[0] or 0) > 0)
    tot = lambda src, i: sum(float((v or [0] * 5)[i] or 0) for v in src.values() if len(v or []) > i)
    spend, impr, clicks, lpv = (round(tot(m, i), 2) for i in range(4))
    checkouts, sales, refunds, commission = int(tot(j, 0)), int(tot(j, 1)), int(tot(j, 2)), round(tot(j, 3), 2)
    cps = st.get('cps')
    revenue = commission if commission or not cps else round(sales * float(cps), 2)
    ads = []
    for aid, ad in ((snap.get('ads') or {}).get(key) or {}).items():
        s = sum(float(v[0] or 0) for v in (ad.get('d') or {}).values())
        if s > 0:
            ads.append({'id': aid, 'name': ad.get('n') or aid, 'campaign': ad.get('c') or '', 'spend': round(s, 2),
                        'clicks': int(sum(float(v[2] or 0) for v in (ad.get('d') or {}).values() if len(v) > 2))})
    ads.sort(key=lambda a: -a['spend'])
    return {'first_day': spend_days[0] if spend_days else st.get('start'), 'last_day': spend_days[-1] if spend_days else None,
            'days': len(spend_days), 'spend': spend, 'impressions': int(impr), 'clicks': int(clicks), 'lpv': int(lpv),
            'checkouts': checkouts, 'sales': sales, 'refunds': refunds, 'revenue': revenue, 'profit': round(revenue - spend, 2),
            'budget': st.get('budget'), 'autopaused_at': st.get('autopausedAt'),
            'daily': {d: round(float(m[d][0] or 0), 2) for d in sorted(m) if m[d] and float(m[d][0] or 0) > 0},
            'top_ads': ads[:5], 'ads_count': len(ads)}


def archive(key, reason, user):
    o = db.q1('select key, name, offer, network, ad_account_id, lander_url, status from offers where key = %s', (key,))
    if not o:
        return {'ok': False, 'error': 'Product not found'}
    if o['status'] == 'archived':
        return {'ok': False, 'error': 'Already in History'}
    paused, pause_error = [], None
    acct = o['ad_account_id']
    shared = acct and db.q1("select 1 from offers where ad_account_id = %s and key <> %s and status <> 'archived'", (acct, key))
    if acct and shared:
        pause_error = 'This ad account is shared with another product, so nothing was paused. Pause its campaigns in Ads Manager.'
    elif acct:
        try:
            for c in meta.active_campaigns(acct):
                with meta.using(acct):
                    meta.pause(c['id'])
                paused.append(c['name'])
        except meta.MetaError as ex:
            pause_error = f'Meta did not confirm the pause ({ex}). Check Ads Manager.'
    snap = _snap()
    rec = {'key': key, 'name': o['name'], 'offer': o['offer'], 'network': o['network'], 'acct': acct, 'lander': o['lander_url'],
           'archived_at': _iso(), 'archived_by': user['email'], 'reason': str(reason or '').strip()[:300],
           'paused_campaigns': paused, 'pause_error': pause_error, **summary(key, snap)}
    db.kv_set(f'history/{key}', rec)
    db.q("update offers set status = 'archived' where key = %s", (key,))
    _set_status_in_snapshot(key, 'archived')
    db.q('insert into budget_events (product, event, detail, amount) values (%s,%s,%s,%s)',
         (key, 'archived', f"Archived by {user['email']}" + (f": {rec['reason']}" if rec['reason'] else '')
          + (f". Paused {len(paused)} campaign(s): {', '.join(paused)}" if paused else ''), rec['spend']))
    return {'ok': True, 'item': rec}


def restore(key, user):
    o = db.q1('select key, status from offers where key = %s', (key,))
    if not o:
        return {'ok': False, 'error': 'Product not found'}
    db.q("update offers set status = 'active' where key = %s", (key,))
    _set_status_in_snapshot(key, 'active')
    db.kv_delete(f'history/{key}')
    db.q('insert into budget_events (product, event, detail, amount) values (%s,%s,%s,%s)',
         (key, 'restored', f"Restored by {user['email']} (ads stay paused until restarted in Ads Manager)", None))
    return {'ok': True}


def items():
    return sorted([r['data'] for r in db.kv_list('history')], key=lambda x: x.get('archived_at') or '', reverse=True)
