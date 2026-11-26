"""ClickBank Instant Notification Service (INS v6-v8) -> events table.

ClickBank POSTs {"notification": base64, "iv": base64}. It is AES-256-CBC; the key is the first 32 hex characters of
sha1(secret key) used as text. The secret key is set by Vlad in ClickBank (Settings -> My Site -> Advanced Tools) and in
Vercel as CLICKBANK_SECRET_KEY (comma-separated if he has several ClickBank accounts). Nothing secret is stored here.

A/B tests: ClickBank only allows letters, numbers, space, _ - + in tracking values, so pages tag ClickBank links with
aff_sub5=<test id><A|B> instead of the ~ suffix used for JVZoo; INS returns it in affiliateTrackingParameters.affSub5."""
import os, json, base64, hashlib
from . import db, abtest

SALE = {'SALE': ('purchase', 'SALE'), 'BILL': ('purchase', 'BILL'), 'RFND': ('purchase', 'RFND'), 'CGBK': ('purchase', 'RFND'),
        'INSF': ('purchase', 'RFND'), 'TEST_SALE': ('purchase', 'SALE'), 'TEST_BILL': ('purchase', 'BILL'),
        'TEST_RFND': ('purchase', 'RFND'), 'TEST': ('purchase', 'SALE'), 'ABANDONED_ORDER': ('initiated', None)}


def configured():
    return bool(_keys())


def _keys():
    return [k.strip() for k in os.environ.get('CLICKBANK_SECRET_KEY', '').split(',') if k.strip()]


def _decrypt(body, secret):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    key = hashlib.sha1(secret.encode()).hexdigest()[:32].encode()
    iv = base64.b64decode(body['iv'])
    ct = base64.b64decode(body['notification'])
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    raw = d.update(ct) + d.finalize()
    pad = raw[-1] if raw else 0
    if 1 <= pad <= 16 and raw.endswith(bytes([pad]) * pad):
        raw = raw[:-pad]
    raw = raw.rstrip(b'\x00 \t\r\n\x10')
    txt = raw.decode('utf-8', errors='replace')
    return json.loads(txt[:txt.rfind('}') + 1])


def decode(raw_body):
    """Returns the notification dict, or None if no key opens it."""
    try:
        body = json.loads(raw_body or b'{}')
    except ValueError:
        return None
    if not isinstance(body, dict) or 'notification' not in body or 'iv' not in body:
        return None
    for k in _keys():
        try:
            n = _decrypt(body, k)
            if isinstance(n, dict) and n.get('receipt'):
                return n
        except Exception:
            continue
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def store(n):
    """One notification -> one events row (sales, rebills, refunds, chargebacks)."""
    typ = str(n.get('transactionType') or '').upper()
    if typ not in SALE:
        return {'ok': True, 'ignored': typ or 'unknown'}
    event, ttype = SALE[typ]
    is_test = typ.startswith('TEST') or str(n.get('paymentMethod') or '').upper() == 'TEST'
    atp = n.get('affiliateTrackingParameters') or {}
    codes = [str(c) for c in (n.get('trackingCodes') or []) if c]
    tid, variant = abtest.parse_tid(codes[0] if codes else None)
    for v in (atp.get('affSub5'), atp.get('uniqueAffSub5')):
        if v and abtest.CODE_RE.match(str(v)):
            variant = str(v)
    items = n.get('lineItems') or []
    first = items[0] if items else {}
    item_no = str(first.get('itemNo') or '')[:60] or None
    vendor = str(n.get('vendor') or '').lower()[:60]
    offers = db.q("select key, offer, network, product_ids from offers where coalesce(network, '') = 'clickbank'")
    ids = lambda o: [str(x).lower() for x in (o['product_ids'] or [])]
    hit = next((o for o in offers if item_no and item_no.lower() in ids(o)), None) or next((o for o in offers if vendor and vendor in ids(o)), None)
    amt = _num(n.get('totalAccountAmount'))
    if ttype == 'RFND' and amt is not None:
        amt = -abs(amt)
    title = ' + '.join(str(i.get('productTitle') or '') for i in items if i.get('productTitle'))[:200] or None
    keep = {k: n.get(k) for k in ('transactionTime', 'receipt', 'transactionType', 'vendor', 'affiliate', 'role', 'paymentMethod',
                                  'totalOrderAmount', 'totalAccountAmount', 'trackingCodes', 'version')}
    keep.update({'affiliateTrackingParameters': atp, 'lineItems': [{k: i.get(k) for k in ('itemNo', 'productTitle', 'accountAmount', 'quantity', 'lineItemType')} for i in items],
                 'country': ((n.get('customer') or {}).get('billing') or {}).get('country')})
    abtest.setup()
    try:
        db.q("""insert into events (network, event, transaction_type, transaction_id, product_id, product_name, product_key, offer, pack,
                                    amount, commission, currency, tid, fbclid, utm_source, utm_campaign, utm_content, country, is_test, raw, variant)
                values ('clickbank',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'USD',%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
             (event, ttype, str(n['receipt'])[:60], item_no, title, hit['key'] if hit else None, (hit['offer'] if hit else None) or title or 'Unknown',
              None, _num(n.get('totalOrderAmount')), amt, tid, (atp.get('fbclid') or None), atp.get('trafficSource'), atp.get('campaign'),
              atp.get('ad') or tid, keep['country'], is_test, db.J(keep), variant))
    except Exception as e:
        if 'events_txn_uq' in str(e) or 'duplicate key' in str(e):
            return {'ok': True, 'duplicate': True}
        raise
    return {'ok': True, 'stored': event, 'variant': variant}


def handle(raw_body):
    """Returns (status, body). ClickBank wants a 2xx within 3 seconds, or it retries every ~4 hours (5 times)."""
    if not _keys():
        return 503, {'ok': False, 'error': 'CLICKBANK_SECRET_KEY is not set in Vercel'}
    n = decode(raw_body)
    if not n:
        return 400, {'ok': False, 'error': 'could not decrypt (wrong secret key?)'}
    try:
        out = store(n)
    except Exception as e:
        return 500, {'ok': False, 'error': str(e)[:200]}
    db.kv_set('_system/clickbank_last', {'at': n.get('transactionTime'), 'type': n.get('transactionType'), 'receipt': n.get('receipt'),
                                          'role': n.get('role'), 'version': n.get('version')})
    return 200, out
