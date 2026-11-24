"""Hero photo options: Claude casts 5-10 clearly different, audience-matched, realistic photos of someone using the product,
checks each one and posts the good ones; the team picks one for the page (or A/B tests two)."""
import copy, datetime, re, secrets
from . import db, agent

SCHEMA = """
alter table pages add column if not exists hero_options jsonb not null default '[]';
alter table pages add column if not exists hero_job jsonb;
"""
_ready = False


def setup():
    global _ready
    if not _ready:
        db.conn().execute(SCHEMA)
        _ready = True


def iso(d=None):
    return (d or datetime.datetime.now(datetime.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')


def busy(row):
    return row['status'] == 'building' or (row.get('test') or {}).get('state') == 'building' or (row.get('hero_job') or {}).get('state') == 'building'


ENGINE_TXT = {
    'openai': "Use engine 'openai' for every row.",
    'higgsfield': ("Use engine 'higgsfield' for every row (Higgsfield SOUL makes the person and scene, then the server places the real "
                   "product into it). For these rows describe the person and scene WITHOUT the product in the prompt, and say where the product "
                   "should go in product_where (e.g. 'in her right hand', 'on the table next to the mug')."),
    '_fallback': " If an engine 'higgsfield' call fails, make that row with engine 'openai' instead (describe the product in the prompt then) and carry on.",
    'mix': ("Alternate engines: odd rows engine 'openai', even rows engine 'higgsfield'. For 'higgsfield' rows describe the person and scene "
            "WITHOUT the product in the prompt and say where it goes in product_where (e.g. 'in her right hand'); the server places the "
            "real product into the photo."),
}


def request(row, count, user, base, tok, tok_hash, audience_text, system_prompt, engine='openai', brief='', like_id=''):
    setup()
    n = 10 if int(count or 5) >= 10 else 5
    have = row.get('hero_options') or []
    used = '; '.join(f"{o.get('person', '')} / {o.get('place', '')} / {o.get('moment', '')}" for o in have[-20:])
    brief = str(brief or '').strip()[:600]
    like = next((o for o in have if o['id'] == like_id), None)
    team = ''
    if brief:
        team += (f"TEAM BRIEF (the most important rule: EVERY row must match it; vary faces, places, moments and framing only within it): {brief}\n")
    if like:
        team += (f"STYLE REFERENCE: the team liked this option: {like.get('person', '')} / {like.get('place', '')} / {like.get('moment', '')} ({like['url']}). "
                 "Match its look (realism, light, framing, how the product is held) but with different people and places. For OpenAI rows pass "
                 "refs:[the product image, " + like['url'] + "] and say in the prompt that the second image is only a style reference, not a person to copy.\n")
    msg = (f"HEROES: make {n} hero photo OPTIONS for this page so the team can pick one. Do NOT change or re-post the page content.\n"
           "1) GET $BASE/api/agent/$PAGE/content to see the product, the angle and product.pack_image (or the pack/product image).\n"
           f"2) Write a casting sheet of {n} rows. Every row is a DIFFERENT person (face, hair colour and style, skin tone, build, glasses or "
           "not, clothes) inside the AUDIENCE below, in a DIFFERENT place (e.g. kitchen table, back porch, home office desk, parked car, "
           "garden, bathroom counter, park bench, sofa, dining room, front steps), at a DIFFERENT moment and time of day, with a DIFFERENT "
           "camera framing (close on hands and product, mid shot, over the shoulder, wide room). No two rows share a place or a moment. "
           "In every row the person is using the product or it is within reach, label readable."
           + (f" These were made before, so do something new: {used}." if used else '') + "\n"
           "3) For each row POST $BASE/api/agent/$PAGE/image {prompt, shape:'landscape', refs:[the product image], engine, product_where} "
           "(up to 3 at a time). Write each prompt as a plain description of that real person, the moment and the place (the server adds "
           "the realism rules). " + ENGINE_TXT.get(engine, ENGINE_TXT['openai']) + (ENGINE_TXT['_fallback'] if engine != 'openai' else '') + "\n"
           "4) Download and LOOK at every result. Reject it if: skin looks plastic or airbrushed, hands or fingers are wrong, the product "
           "label is garbled or different from the reference, there is any added text, it looks like AI art or a stock photo, or the person "
           "is outside the audience. Remake a rejected row once with a plainer, more specific prompt; drop it if it fails again.\n"
           "5) POST each image that passes to $BASE/api/agent/$PAGE/hero_option {url, person, place, moment, camera, alt, caption, engine} "
           "(short plain words; caption <= 90 chars, describes the moment, never names or calls the person a customer).\n"
           f"6) Reply 'DONE: <number> options' and one line on anything the team should know.\n" + team
           + (audience_text + '\n' if audience_text else '') +
           f"\nPAGE={row['id']}\nBASE={base}\nPAGE_TOKEN={tok}")
    job = {'state': 'building', 'count': n, 'started_at': iso(), 'by': user['email'], 'before': len(have), 'engine': engine,
           'brief': brief, 'like': like_id if like else ''}
    try:
        alive = False
        if row.get('session_id'):
            try:
                alive = (agent.session(row['session_id']).get('status') or '') in ('idle', 'running')
            except Exception:
                alive = False
        if alive:
            agent.send(row['session_id'], msg)
            job['session_id'] = row['session_id']
        else:
            s = agent.start_session(system_prompt(), f"hero options: {row.get('name') or row['slug']}", msg, row['id'])
            job['session_id'] = s.get('id')
    except Exception as e:
        return {'ok': False, 'error': f'Claude could not start: {str(e)[:200]}'}
    db.q('update pages set hero_job = %s, token_hash = %s, updated_at = now() where id = %s', (db.J(job), tok_hash, row['id']))
    return {'ok': True}


def add_option(row, data, base):
    setup()
    url = str(data.get('url') or '')
    if not re.match(r'^' + re.escape(base) + r'/u/[A-Za-z0-9_-]{20,40}\.(png|jpg|webp)$', url):
        return {'ok': False, 'error': 'url must be an image made with this page\'s /image endpoint'}
    if (row.get('hero_job') or {}).get('state') != 'building':
        return {'ok': False, 'error': 'no hero options were requested'}
    t = lambda k, n=120: str(data.get(k) or '').strip()[:n]
    opt = {'id': secrets.token_hex(4), 'url': url, 'person': t('person'), 'place': t('place'), 'moment': t('moment'), 'camera': t('camera'),
           'alt': t('alt', 200), 'caption': t('caption', 90), 'at': iso(),
           'engine': 'higgsfield' if str(data.get('engine') or '') == 'higgsfield' else 'openai'}
    db.q("""update pages set hero_options = (case when jsonb_array_length(hero_options) >= 40 then hero_options - 0 else hero_options end) || %s::jsonb,
            updated_at = now() where id = %s""", (db.J([opt]), row['id']))
    return {'ok': True, 'id': opt['id']}


def check(row):
    j = row.get('hero_job') or {}
    if j.get('state') != 'building' or not j.get('session_id'):
        return row
    try:
        started = datetime.datetime.fromisoformat(j['started_at'].replace('Z', '+00:00'))
        st = agent.session(j['session_id']).get('status') or ''
    except Exception:
        return row
    age = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
    made = len(row.get('hero_options') or []) - int(j.get('before') or 0)
    if (st in ('idle', 'terminated') and age > 120) or age > 40 * 60:
        j.update({'state': 'done' if made > 0 else 'failed', 'made': made, 'ended_at': iso()})
        if made <= 0:
            j['error'] = (agent.last_words(j['session_id']) or 'Claude stopped before making any photos.')[:400]
        db.q('update pages set hero_job = %s, updated_at = now() where id = %s', (db.J(j), row['id']))
        row = {**row, 'hero_job': j}
    return row


def _with_hero(content, opt):
    c = copy.deepcopy(content)
    h = c.setdefault('hero', {})
    h['image'] = opt['url']
    if opt.get('alt'):
        h['alt'] = opt['alt']
    if opt.get('caption'):
        h['caption'] = opt['caption']
    return c


def use(row, oid):
    opt = next((o for o in row.get('hero_options') or [] if o['id'] == oid), None)
    if not opt or not row.get('content'):
        return {'ok': False, 'error': 'Photo not found'}
    db.q('update pages set content = %s, updated_at = now() where id = %s', (db.J(_with_hero(row['content'], opt)), row['id']))
    return {'ok': True}


def test(row, ids):
    """1 photo: current page vs that photo. 2 photos: first goes on the page (A), second becomes B."""
    opts = {o['id']: o for o in row.get('hero_options') or []}
    ids = [i for i in ids if i in opts][:2]
    if not ids:
        return {'ok': False, 'error': 'Pick one or two photos'}
    if (row.get('test') or {}).get('state') in ('building', 'running', 'ready'):
        return {'ok': False, 'error': 'This page already has an A/B test. Finish or throw it away first.'}
    content = row['content']
    if len(ids) == 2:
        content = _with_hero(content, opts[ids[0]])
    b = _with_hero(content, opts[ids[-1]])
    t = {'id': secrets.token_hex(2), 'state': 'ready', 'focus': 'photo', 'photo': True, 'note': 'Picked from hero options', 'b': b,
         'created_at': iso(), 'ready_at': iso(), 'auto': True}
    db.q('update pages set content = %s, test = %s, updated_at = now() where id = %s', (db.J(content), db.J(t), row['id']))
    return {'ok': True}


def remove(row, oid):
    db.q("""update pages set hero_options = coalesce((select jsonb_agg(o) from jsonb_array_elements(hero_options) o where o->>'id' <> %s), '[]'::jsonb),
            updated_at = now() where id = %s""", (oid, row['id']))
    return {'ok': True}


def public(row):
    return {'hero_brief': (row.get('hero_job') or {}).get('brief') or '', 'hero_options': row.get('hero_options') or [], 'hero_job': {k: v for k, v in (row.get('hero_job') or {}).items() if k != 'session_id'} or None,
            'hero_image': ((row.get('content') or {}).get('hero') or {}).get('image')}
