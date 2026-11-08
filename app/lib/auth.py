"""Login: team members live in kv team/<id> {name, email, role, note, pwHash}. Sessions are signed cookies."""
import os, hmac, hashlib, base64, json, time, secrets, datetime
from . import db

COOKIE = 'nutra_session'
DAYS = 30


def owner_email():
    return (os.environ.get('OWNER_EMAIL') or '').strip().lower()


def _secret():
    s = db.kv_data('_system/secret')
    if not s:
        db.kv_set('_system/secret', {'v': secrets.token_hex(32)})
        s = db.kv_data('_system/secret')
    return s['v'].encode()


def hash_pw(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(h).decode()


def check_pw(pw, stored):
    try:
        _, salt, h = stored.split('$')
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:
        return False


def members():
    return [{'id': r['path'].split('/', 1)[1], **r['data']} for r in db.kv_list('team')]


def find_all(email):
    email = (email or '').strip().lower()
    return [m for m in members() if (m.get('email') or '').strip().lower() == email] if email else []


def find(email):
    """The member with this email; if there are duplicates, the one that has a password wins."""
    ms = find_all(email)
    return next((m for m in ms if m.get('pwHash')), ms[0] if ms else None)


def role_of(m):
    if not m:
        return None
    if owner_email() and (m.get('email') or '').lower() == owner_email():
        return 'owner'
    return 'editor' if m.get('role') in ('editor', 'owner') else 'viewer'


def needs_setup():
    """True until the owner has set a password."""
    o = find(owner_email()) if owner_email() else None
    return not (o and o.get('pwHash'))


def make_cookie(email):
    body = base64.urlsafe_b64encode(json.dumps({'e': email.lower(), 'x': int(time.time()) + DAYS * 86400}).encode()).decode()
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f'{body}.{sig}'


def read_cookie(raw):
    try:
        body, sig = raw.rsplit('.', 1)
        if not hmac.compare_digest(sig, hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()):
            return None
        d = json.loads(base64.urlsafe_b64decode(body.encode()))
        if d['x'] < time.time():
            return None
        m = find(d['e'])
        if not m or not m.get('pwHash'):
            return None
        return {'email': m['email'].lower(), 'name': m.get('name') or '', 'id': m['id'], 'role': role_of(m)}
    except Exception:
        return None


def login(email, pw):
    for m in find_all(email):
        if m.get('pwHash') and check_pw(pw or '', m['pwHash']):
            return m
    return None


def reset_code():
    """Owner password reset is only open while OWNER_RESET_CODE (8+ chars) is set in Vercel."""
    c = (os.environ.get('OWNER_RESET_CODE') or '').strip()
    return c if len(c) >= 8 else ''


# ── Claude scheduled-task access key (Bearer nk_...). Only its hash is stored. ──
AGENT = {'email': 'claude-task@nutra', 'name': 'Claude (scheduled task)', 'id': '_agent', 'role': 'agent'}


def new_agent_key():
    key = 'nk_' + secrets.token_urlsafe(32)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.kv_set('_system/agent_key', {'hash': hashlib.sha256(key.encode()).hexdigest(), 'createdAt': now, 'lastUsed': None})
    return key


def agent_key_status():
    d = db.kv_data('_system/agent_key') or {}
    return {'exists': bool(d.get('hash')), 'createdAt': d.get('createdAt'), 'lastUsed': d.get('lastUsed')}


def agent_from_bearer(header):
    if not header or not header.startswith('Bearer nk_'):
        return None
    d = db.kv_data('_system/agent_key') or {}
    h = hashlib.sha256(header[7:].strip().encode()).hexdigest()
    if not d.get('hash') or not hmac.compare_digest(h, d['hash']):
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        stale = not d.get('lastUsed') or (now - datetime.datetime.fromisoformat(d['lastUsed'])).total_seconds() > 600
    except ValueError:
        stale = True
    if stale:
        db.kv_set('_system/agent_key', {**d, 'lastUsed': now.isoformat()})
    return dict(AGENT)
