"""Network postbacks (JVZoo sales, checkout starts) and lander buy-button clicks -> events table."""
import re, hmac
from . import db

PACKS = {'446243': '2 Bottles', '446537': '2 Pack', '447307': '3 Pack', '447309': '6 Pack', '451967': '2 Bottles',
         '451969': '3 Bottles', '451971': '6 Bottles', '457697': '3 Bottles Upsell', '457713': '6 Bottles Upsell',
         '453339': '2 Bottles', '453343': '3 Bottles', '453345': '6 Bottles'}


def clean(v):
    """Empty strings and unfilled macros like {fbclid} become None."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or (s.startswith('{') and s.endswith('}')):
        return None
    return s[:500]


def money(v):
    s = clean(v)
    if s is None:
        return None
    s = re.sub(r'[^0-9.\-]', '', s)
    try:
        return float(s) if s else None
    except ValueError:
        return None


def key_ok(given):
    pb = db.kv_data('private/postback') or {}
    want = pb.get('key')
    return bool(want and given and hmac.compare_digest(str(given), str(want)))


def handle(params, forced_network=None):
    """Returns (status, body)."""
    if not key_ok(params.get('key')):
        return 401, {'ok': False}
    if params.get('ping') == '1':
        return 200, {'ok': True, 'ping': True}
    p = lambda k: clean(params.get(k))
    network = (forced_network or p('network') or 'jvzoo').lower()[:50]
    product_id = p('product_id')
    offers = db.q('select key, offer, network, product_ids from offers')
    hit = None
    if product_id:
        hit = next((o for o in offers if (o['network'] or 'jvzoo') == network and product_id in [str(x) for x in (o['product_ids'] or [])]), None)
    if not hit and p('offer'):
        hit = next((o for o in offers if o['key'] == p('offer')), None)
    typ = p('type')
    raw = {k: str(v)[:500] for k, v in params.items() if k != 'key'}
    try:
        db.q("""insert into events (network, event, transaction_type, transaction_id, product_id, product_name, product_key, offer, pack,
                                    amount, commission, currency, tid, fbclid, utm_source, utm_campaign, utm_content, country, is_test, raw)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
             (network, (p('event') or 'purchase').lower()[:30], typ.upper() if typ else None, p('txn'), product_id, p('product_name'),
              hit['key'] if hit else None, (hit['offer'] if hit else None) or 'Unknown', PACKS.get(product_id or ''),
              money(params.get('amount')), money(params.get('commission')), p('currency'), p('tid'), p('fbclid'),
              p('utm_source'), p('utm_campaign'), p('utm_content'), p('country'), p('test') == '1', db.J(raw)))
    except Exception as e:
        if 'events_txn_uq' in str(e) or 'duplicate key' in str(e):
            return 200, {'ok': True, 'duplicate': True}
        return 200, {'ok': True, 'stored': False}
    return 200, {'ok': True}
