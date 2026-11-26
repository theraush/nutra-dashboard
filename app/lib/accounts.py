"""Ad accounts screen: Facebook connections (system-user tokens) and which ad account runs which offer.

kv private/meta/conns     {conn_id: {name, token, added_by, added_at}}   (owners/editors only; tokens never sent to the page)
kv private/meta/accounts  {account_id: conn_id}                          ('default' = META_TOKEN in Vercel)
kv private/meta/cache     {at, accounts: [{id, name, status, currency, business, conn}], errors: {conn_id: text}}
Offers keep their account in offers.ad_account_id (the hourly sync reads it). Pages point to an offer with pages.offer_key."""
import os, re, secrets, datetime
from . import db, meta

STATUS = {1: 'Active', 2: 'Disabled', 3: 'Unsettled', 7: 'Pending review', 9: 'In grace period', 100: 'Pending closure', 101: 'Closed'}
KEY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,30}$')


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def conns():
    return db.kv_data('private/meta/conns') or {}


def refresh():
    """Ask every connection which ad accounts it can see; remember which connection owns each account."""
    out, amap, errs = [], {}, {}
    cs = [('default', {'name': 'Main connection (Vercel)', 'token': os.environ.get('META_TOKEN')})] + list(conns().items())
    for cid, c in cs:
        if not c.get('token'):
            continue
        try:
            for a in meta.accounts_for(c['token']):
                if a['id'] in amap:
                    continue
                amap[a['id']] = cid
                out.append({**a, 'status': STATUS.get(a.get('status'), str(a.get('status') or '')), 'conn': cid})
        except Exception as e:
            errs[cid] = str(e)[:200]
    db.kv_set('private/meta/accounts', amap)
    data = {'at': now(), 'accounts': out, 'errors': errs}
    db.kv_set('private/meta/cache', data)
    meta.forget_tokens()
    return data


def view(fresh=False):
    cache = db.kv_data('private/meta/cache') or {}
    if fresh or not cache.get('at'):
        cache = refresh()
    cl = [{'id': 'default', 'name': 'Main connection (Vercel)', 'builtin': True, 'ok': bool(os.environ.get('META_TOKEN')) and 'default' not in cache.get('errors', {})}]
    for cid, c in conns().items():
        cl.append({'id': cid, 'name': c.get('name') or cid, 'added_at': c.get('added_at'), 'added_by': c.get('added_by'), 'ok': cid not in cache.get('errors', {})})
    for c in cl:
        c['count'] = sum(1 for a in cache.get('accounts', []) if a['conn'] == c['id'])
        c['error'] = cache.get('errors', {}).get(c['id'])
    offers = db.q("select key, name, offer, network, ad_account_id, status, color from offers where coalesce(status,'active') <> 'archived' order by sort, created_at")
    return {'ok': True, 'connections': cl, 'accounts': cache.get('accounts', []), 'checked_at': cache.get('at'), 'offers': offers}


def connect(name, token, user):
    token = str(token or '').strip()
    name = str(name or '').strip()[:60] or 'Facebook connection'
    if len(token) < 30 or not re.match(r'^[A-Za-z0-9_\-|.]+$', token):
        return {'ok': False, 'error': 'That does not look like a Facebook access token. Copy the whole token from Business Settings → System users.'}
    try:
        accts = meta.accounts_for(token)
    except Exception as e:
        return {'ok': False, 'error': 'Facebook rejected this token: ' + str(e)[:160]}
    if not accts:
        return {'ok': False, 'error': 'The token works, but it has no ad accounts. In Business Settings, assign the ad accounts to this system user (Full control or Advertise), then try again.'}
    cs = conns()
    cid = 'c' + secrets.token_hex(3)
    cs[cid] = {'name': name, 'token': token, 'added_by': user.get('email'), 'added_at': now()}
    db.kv_set('private/meta/conns', cs)
    refresh()
    return {'ok': True, 'id': cid, 'found': len(accts)}


def remove(cid):
    cs = conns()
    if cid not in cs:
        return {'ok': False, 'error': 'Connection not found'}
    cs.pop(cid)
    db.kv_set('private/meta/conns', cs)
    refresh()
    return {'ok': True}


def map_offer(key, acct):
    acct = re.sub(r'[^0-9]', '', str(acct or ''))
    if not db.q1('select 1 as x from offers where key = %s', (key,)):
        return {'ok': False, 'error': 'Offer not found'}
    db.q('update offers set ad_account_id = %s, pixel_id = case when ad_account_id is distinct from %s then null else pixel_id end where key = %s',
         (acct or None, acct or None, key))
    return {'ok': True}


def setup():
    db.q("alter table pages add column if not exists offer_key text")


def create_offer(page, acct, user, ids=None):
    """Make an offer for a page (so its ads and sales show on Home) and link it to an ad account."""
    acct = re.sub(r'[^0-9]', '', str(acct or ''))
    if not acct:
        return {'ok': False, 'error': 'Pick an ad account'}
    key = (page.get('offer_key') or re.sub(r'[^a-z0-9-]', '', str(page.get('slug') or ''))[:30] or 'page').lower()
    if not KEY_RE.match(key):
        key = 'p' + secrets.token_hex(3)
    i = page.get('input') or {}
    lander = ('https://' + page['domain']) if page.get('domain') else ''
    name = page.get('name') or i.get('name') or key
    color = ['#16A34A', '#2563EB', '#DB2777', '#7C3AED', '#D97706'][sum(map(ord, key)) % 5]
    ids = [x for x in re.split(r'[\s,]+', str(ids or '').lower()) if re.match(r'^[a-z0-9_-]{2,40}$', x)][:10]
    db.q("""insert into offers (key, name, offer, network, ad_account_id, lander_url, color, status, sort, product_ids)
            values (%s,%s,%s,%s,%s,%s,%s,'active',(select coalesce(max(sort),0)+1 from offers),%s)
            on conflict (key) do update set ad_account_id = excluded.ad_account_id, status = 'active',
              product_ids = case when jsonb_array_length(excluded.product_ids) > 0 then excluded.product_ids else offers.product_ids end""",
         (key, name, name, i.get('network') or 'jvzoo', acct, lander, color, db.J(ids)))
    db.q('update pages set offer_key = %s, updated_at = now() where id = %s', (key, page['id']))
    return {'ok': True, 'key': key}
