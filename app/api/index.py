"""NUTRA dashboard on Vercel: one Python (WSGI) function serves every route (see vercel.json)."""
import os, sys, json, re, html, hmac, urllib.parse, secrets
from http.cookies import SimpleCookie

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import db, auth, postback, sync  # noqa: E402

STATIC = os.path.join(ROOT, 'static')
PATH_RE = re.compile(r'^[A-Za-z0-9_\-.~:@+]{1,200}/[A-Za-z0-9_\-.~:@+]{1,200}$')
SECURE = os.environ.get('VERCEL') == '1'


def read_static(name):
    with open(os.path.join(STATIC, name), encoding='utf-8') as f:
        return f.read()


# ── tiny response helpers ──
class Resp:
    def __init__(self, status=200, body=b'', ctype='text/html; charset=utf-8', headers=None):
        self.status, self.body, self.headers = status, body if isinstance(body, bytes) else body.encode(), [('Content-Type', ctype)] + (headers or [])


def jresp(obj, status=200, headers=None):
    return Resp(status, json.dumps(obj, default=str), 'application/json', [('Cache-Control', 'no-store')] + (headers or []))


def redirect(to, headers=None):
    return Resp(302, b'', 'text/plain', [('Location', to)] + (headers or []))


def cookie_header(value, max_age):
    c = f'{auth.COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}'
    return ('Set-Cookie', c + ('; Secure' if SECURE else ''))


STATUS = {200: '200 OK', 302: '302 Found', 400: '400 Bad Request', 401: '401 Unauthorized', 403: '403 Forbidden',
          404: '404 Not Found', 405: '405 Method Not Allowed', 409: '409 Conflict', 500: '500 Internal Server Error', 503: '503 Service Unavailable'}


# ── request parsing ──
def params_of(env, body):
    out = {}
    if body:
        ct = env.get('CONTENT_TYPE', '')
        if 'json' in ct:
            try:
                j = json.loads(body)
                if isinstance(j, dict):
                    out.update({k: v for k, v in j.items()})
            except ValueError:
                pass
        else:
            out.update({k: v for k, v in urllib.parse.parse_qsl(body.decode(errors='replace'), keep_blank_values=True)})
    out.update({k: v for k, v in urllib.parse.parse_qsl(env.get('QUERY_STRING', ''), keep_blank_values=True)})
    return out


def current_user(env):
    c = SimpleCookie(env.get('HTTP_COOKIE', ''))
    m = c.get(auth.COOKIE)
    return auth.read_cookie(m.value) if m else None


def same_origin(env):
    """Block cross-site form posts to state-changing endpoints."""
    o = env.get('HTTP_ORIGIN')
    if not o:
        return True
    return urllib.parse.urlparse(o).netloc == env.get('HTTP_HOST')


# ── pages ──
def auth_page(title, sub, fields, button, error='', action=''):
    inputs = ''.join(f'<label>{html.escape(l)}<input name="{n}" type="{t}" autocomplete="{ac}" required{" autofocus" if i == 0 else ""}></label>'
                     for i, (l, n, t, ac) in enumerate(fields))
    return read_static('auth.html').replace('{{TITLE}}', html.escape(title)).replace('{{SUB}}', sub).replace('{{FIELDS}}', inputs) \
        .replace('{{BUTTON}}', html.escape(button)).replace('{{ERROR}}', f'<p class="err" role="alert">{html.escape(error)}</p>' if error else '') \
        .replace('{{ACTION}}', action)


def dashboard_page(user):
    page = read_static('dashboard.html')
    snap = db.q1('select data from snapshot where id = 1')
    if snap:
        data = json.dumps(snap['data'], separators=(',', ':'), ensure_ascii=False).replace('</', '<\\/')
        page = re.sub(r'const DATA = \{.*?\};\n', lambda m: 'const DATA = ' + data + ';\n', page, count=1, flags=re.S)
    me = json.dumps({'id': user['id'], 'email': user['email'], 'name': user['name'], 'role': user['role']}).replace('</', '<\\/')
    head = read_static('head.html')
    return head + f'<script>window.NUTRA_HOSTED=true;window.NUTRA_ME={me};</script><script>{read_static("shim.js")}</script>\n' + page + '\n</body></html>'


# ── /api/db: the Settings tab's documents ──
def visible(path, role):
    if path.startswith('_system/'):
        return False
    if path.startswith('private/') and role not in ('owner', 'editor'):
        return False
    return True


def public_doc(path, data):
    if path.startswith('team/'):
        data = {k: v for k, v in data.items() if k != 'pwHash'}
        data['hasPassword'] = bool((db.kv_data(path) or {}).get('pwHash')) if 'hasPassword' not in data else data['hasPassword']
    return data


def api_db(user, p):
    op, path = p.get('op'), p.get('path')
    if op == 'all':
        docs = []
        for r in db.kv_all():
            if not visible(r['path'], user['role']):
                continue
            d = dict(r['data'])
            if r['path'].startswith('team/'):
                d['hasPassword'] = bool(d.pop('pwHash', None))
            docs.append({'path': r['path'], 'data': d, 'version': r['version']})
        return jresp({'ok': True, 'docs': docs})
    if user['role'] not in ('owner', 'editor'):
        return jresp({'ok': False, 'error': 'View only: ask the owner for Editor access', 'code': 'forbidden'}, 403)
    if not isinstance(path, str) or not PATH_RE.match(path) or not visible(path, user['role']) or path.startswith('snapshot'):
        return jresp({'ok': False, 'error': 'Not allowed'}, 403)
    cur = db.kv_data(path)
    if path.startswith('team/'):
        target = (cur or {}).get('email', '') if op == 'delete' else str((p.get('data') or {}).get('email') or (cur or {}).get('email') or '')
        if target.lower() == auth.owner_email() and user['role'] != 'owner':
            return jresp({'ok': False, 'error': 'Only the owner can change the owner'}, 403)
        if op == 'delete' and target.lower() == auth.owner_email():
            return jresp({'ok': False, 'error': "The owner can't be removed"}, 403)
    if op == 'delete':
        db.kv_delete(path)
        return jresp({'ok': True})
    data = p.get('data')
    if not isinstance(data, dict):
        return jresp({'ok': False, 'error': 'data must be an object'}, 400)
    if len(json.dumps(data)) > 200_000:
        return jresp({'ok': False, 'error': 'too large'}, 400)
    if op == 'update':
        data = {**(cur or {}), **data}
        data = {k: v for k, v in data.items() if not (isinstance(v, dict) and v.get('__delete__'))}
    elif op != 'set':
        return jresp({'ok': False, 'error': 'unknown op'}, 400)
    if path.startswith('team/'):
        data.pop('hasPassword', None)
        pw = data.pop('password', None)
        data['email'] = str(data.get('email') or '').strip().lower()
        if pw:
            if len(str(pw)) < 8:
                return jresp({'ok': False, 'error': 'Password needs at least 8 characters'}, 400)
            data['pwHash'] = auth.hash_pw(str(pw))
        elif cur and cur.get('pwHash'):
            data['pwHash'] = cur['pwHash']
    db.kv_set(path, data)
    return jresp({'ok': True})


# ── one-time import from the old setup (owner only) ──
def api_import(p):
    n = {}
    for o in p.get('offers') or []:
        db.q("""insert into offers (key,name,offer,network,ad_account_id,pixel_id,lander_url,buy_links,product_ids,color,status,sort,budget,
                                    start_date,warn_at,auto_pause,commission_per_sale,autopaused_at,warn_alerted_at,depleted_alerted_at)
                values (%(key)s,%(name)s,%(offer)s,%(network)s,%(ad_account_id)s,%(pixel_id)s,%(lander_url)s,%(buy_links)s,%(product_ids)s,%(color)s,
                        %(status)s,%(sort)s,%(budget)s,%(start_date)s,%(warn_at)s,%(auto_pause)s,%(commission_per_sale)s,%(autopaused_at)s,
                        %(warn_alerted_at)s,%(depleted_alerted_at)s)
                on conflict (key) do update set name=excluded.name, offer=excluded.offer, network=excluded.network, ad_account_id=excluded.ad_account_id,
                  pixel_id=excluded.pixel_id, lander_url=excluded.lander_url, buy_links=excluded.buy_links, product_ids=excluded.product_ids,
                  color=excluded.color, status=excluded.status, sort=excluded.sort, budget=excluded.budget, start_date=excluded.start_date,
                  warn_at=excluded.warn_at, auto_pause=excluded.auto_pause, commission_per_sale=excluded.commission_per_sale,
                  autopaused_at=excluded.autopaused_at, warn_alerted_at=excluded.warn_alerted_at, depleted_alerted_at=excluded.depleted_alerted_at""",
             {**{f: None for f in ('offer', 'network', 'ad_account_id', 'pixel_id', 'lander_url', 'color', 'start_date', 'commission_per_sale',
                                    'autopaused_at', 'warn_alerted_at', 'depleted_alerted_at')},
              'status': 'active', 'sort': 0, 'budget': 0, 'warn_at': 70, 'auto_pause': True, **o,
              'buy_links': db.J(o.get('buy_links') or []), 'product_ids': db.J(o.get('product_ids') or [])})
        n['offers'] = n.get('offers', 0) + 1
    for e in p.get('events') or []:
        try:
            db.q("""insert into events (received_at, network, event, transaction_type, transaction_id, product_id, product_name, product_key, offer,
                                        pack, amount, commission, currency, tid, fbclid, utm_source, utm_campaign, utm_content, country, is_test, raw)
                    values (%(received_at)s, coalesce(%(network)s,'jvzoo'), %(event)s, %(transaction_type)s, %(transaction_id)s, %(product_id)s,
                            %(product_name)s, %(product_key)s, %(offer)s, %(pack)s, %(amount)s, %(commission)s, %(currency)s, %(tid)s, %(fbclid)s,
                            %(utm_source)s, %(utm_campaign)s, %(utm_content)s, %(country)s, coalesce(%(is_test)s,false), %(raw)s)
                    on conflict do nothing""",
                 {**{f: None for f in ('network', 'transaction_type', 'transaction_id', 'product_id', 'product_name', 'product_key', 'offer', 'pack',
                                        'amount', 'commission', 'currency', 'tid', 'fbclid', 'utm_source', 'utm_campaign', 'utm_content', 'country', 'is_test')},
                  **e, 'raw': db.J(e.get('raw') or {})})
            n['events'] = n.get('events', 0) + 1
        except Exception:
            pass
    for x in p.get('notes') or []:
        db.q('insert into notes (day, product, text) values (%s,%s,%s)', (x['day'], x.get('product'), x['text']))
        n['notes'] = n.get('notes', 0) + 1
    for path, data in (p.get('kv') or {}).items():
        if PATH_RE.match(path) and not path.startswith('_system/') and isinstance(data, dict):
            if path.startswith('team/'):
                same = auth.find(data.get('email'))
                if same and f"team/{same['id']}" != path:  # already on the team (e.g. the owner from setup): merge, keep that doc
                    path = f"team/{same['id']}"
                    data = {**{k: v for k, v in same.items() if k != 'id'}, **{k: v for k, v in data.items() if k not in ('role',)}}
                old = db.kv_data(path) or {}
                data = {**data, 'email': str(data.get('email') or '').lower(), **({'pwHash': old['pwHash']} if old.get('pwHash') else {})}
            db.kv_set(path, data)
            n['kv'] = n.get('kv', 0) + 1
    if isinstance(p.get('snapshot'), dict):
        db.q("insert into snapshot (id, data) values (1, %s) on conflict (id) do update set data = excluded.data, at = now()", (db.J(p['snapshot']),))
        n['snapshot'] = 1
    return jresp({'ok': True, 'imported': n})


def ensure_postback_key():
    pb = db.kv_data('private/postback') or {}
    if not pb.get('key'):
        db.kv_set('private/postback', {**pb, 'key': 'nt_' + secrets.token_urlsafe(24)})


def cron_ok(env, p):
    want = os.environ.get('CRON_SECRET')
    if not want:
        return False
    got = (env.get('HTTP_AUTHORIZATION') or '').removeprefix('Bearer ').strip() or str(p.get('key') or '')
    return hmac.compare_digest(got, want)


# ── router ──
def route(env):
    method, path = env['REQUEST_METHOD'], env.get('PATH_INFO') or '/'
    try:
        n = int(env.get('CONTENT_LENGTH') or 0)
    except ValueError:
        n = 0
    body = env['wsgi.input'].read(min(n, 1_000_000)) if n else b''
    p = params_of(env, body)
    host = env.get('HTTP_HOST', '')

    if path == '/api/health':
        try:
            db.q1('select 1')
            return jresp({'ok': True, 'db': True, 'meta': bool(os.environ.get('META_TOKEN')), 'cron': bool(os.environ.get('CRON_SECRET'))})
        except Exception as e:
            return jresp({'ok': False, 'db': False, 'error': str(e)[:200]}, 503)

    if path in ('/api/public/postback', '/api/public/jvzoo-postback'):
        status, out = postback.handle(p, 'jvzoo' if path.endswith('jvzoo-postback') else None)
        return jresp(out, status)

    if path == '/api/cron':
        user = current_user(env)
        if cron_ok(env, p) or (user and user['role'] in ('owner', 'editor') and method == 'POST' and same_origin(env)):
            return jresp(sync.run())
        # Anyone (e.g. an hourly pinger) may start a sync, but at most once every 25 minutes; nothing is returned but status.
        last = db.kv_data('config/sync') or {}
        try:
            import datetime
            age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(str(last.get('at')).replace('Z', '+00:00'))).total_seconds()
        except (TypeError, ValueError):
            age = 1e9
        if age < 25 * 60:
            return jresp({'ok': True, 'skipped': 'synced recently', 'at': last.get('at')})
        r = sync.run()
        return jresp({'ok': r.get('ok'), 'summary': r.get('summary'), 'errors': len(r.get('errors') or [])})

    # first run: the owner (OWNER_EMAIL) sets a password
    if path == '/setup':
        if not auth.needs_setup():
            return redirect('/login')
        if not auth.owner_email():
            return Resp(503, auth_page('Almost there', 'Set <b>OWNER_EMAIL</b> in Vercel → Settings → Environment Variables, then redeploy.', [], 'Reload', action='/setup'))
        sub = 'Create the owner password for <b>' + html.escape(auth.owner_email()) + '</b>.'
        if method == 'POST' and same_origin(env):
            pw = str(p.get('password') or '')
            if len(pw) < 10:
                return Resp(400, auth_page('Set up NUTRA', sub, [('Password (10+ characters)', 'password', 'password', 'new-password')], 'Create owner login', 'Use at least 10 characters.', '/setup'))
            m = auth.find(auth.owner_email())
            path_ = f"team/{m['id']}" if m else 'team/owner'
            base = {k: v for k, v in (m or {}).items() if k != 'id'}
            db.kv_set(path_, {'name': base.get('name') or 'Owner', 'note': base.get('note') or 'Owner', **base,
                              'email': auth.owner_email(), 'role': 'editor', 'pwHash': auth.hash_pw(pw)})
            ensure_postback_key()
            return redirect('/', [cookie_header(auth.make_cookie(auth.owner_email()), auth.DAYS * 86400)])
        return Resp(200, auth_page('Set up NUTRA', sub, [('Password (10+ characters)', 'password', 'password', 'new-password')], 'Create owner login', action='/setup'))

    if path == '/login':
        if auth.needs_setup():
            return redirect('/setup')
        fields = [('Email', 'email', 'email', 'username'), ('Password', 'password', 'password', 'current-password')]
        if method == 'POST' and same_origin(env):
            m = auth.login(p.get('email'), p.get('password'))
            if m:
                return redirect('/', [cookie_header(auth.make_cookie(m['email']), auth.DAYS * 86400)])
            return Resp(401, auth_page('NUTRA', 'Sign in to the dashboard.', fields, 'Sign in', 'Wrong email or password.', '/login'))
        return Resp(200, auth_page('NUTRA', 'Sign in to the dashboard.', fields, 'Sign in', action='/login'))

    if path == '/logout':
        return redirect('/login', [cookie_header('', 0)])

    user = current_user(env)
    if path == '/api/db':
        if not user:
            return jresp({'ok': False, 'error': 'signed out'}, 401)
        if method != 'POST' or not same_origin(env):
            return jresp({'ok': False}, 405)
        return api_db(user, p)

    if path == '/api/admin/import':
        if not user or user['role'] != 'owner' or method != 'POST' or not same_origin(env):
            return jresp({'ok': False}, 403)
        return api_import(p)

    if path in ('/', '/index.html'):
        if not user:
            return redirect('/setup' if auth.needs_setup() else '/login')
        return Resp(200, dashboard_page(user), headers=[('Cache-Control', 'no-store'), ('X-Frame-Options', 'DENY'), ('Referrer-Policy', 'same-origin')])

    if path == '/favicon.ico':
        return Resp(204 if False else 404, b'', 'text/plain')
    return Resp(404, 'Not found', 'text/plain')


def app(env, start_response):
    try:
        r = route(env)
    except Exception as e:  # never leak a stack trace to the browser
        import traceback
        traceback.print_exc()
        r = jresp({'ok': False, 'error': 'Server error: ' + type(e).__name__ + (': ' + str(e)[:160] if 'DATABASE_URL' in str(e) else '')}, 500)
    start_response(STATUS.get(r.status, f'{r.status} Status'), r.headers + [('X-Content-Type-Options', 'nosniff')])
    return [r.body]
