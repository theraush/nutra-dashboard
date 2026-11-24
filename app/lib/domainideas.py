"""Domain ideas for a page: Claude suggests neutral editorial .com names that fit the product and audience,
then each one is checked against the .com registry (RDAP) so only names that are still free show up."""
import os, json, re, datetime, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from . import db, agent

KV = 'domain_ideas/'
NAME_RE = re.compile(r'^[a-z][a-z]{2,24}\.com$')
SUB_RE = re.compile(r'^[a-z]{2,14}$')
BANNED = ('cure', 'heal', 'doctor', 'dr', 'clinic', 'pharma', 'rx', 'fda', 'medic', 'facebook', 'meta', 'insta', 'google',
          'clickbank', 'jvzoo', 'amazon', 'cancer', 'diabet', 'alzheim', 'dementia', 'covid', 'miracle', 'guarant')

PROMPT = """You name websites for affiliate advertorial pages. Suggest {n} .com domain names for the page below.

The domain is the main site; this page will live on a subdomain of it (e.g. memory.example.com), and future pages for
other health and wellness products (sleep, energy, joints, blood sugar…) will reuse the same domain on other subdomains.
So the domain must sound like a calm, neutral health and lifestyle magazine or daily tips site for THIS audience, not like
this one product.

Rules:
- 2 or 3 plain English words joined, letters only, no hyphens or numbers, 8 to 20 letters before .com, easy to say and spell.
- Trustworthy, editorial, friendly to the audience (e.g. "daily", "notes", "journal", "report", "living", "routine", "digest").
- Never use: the product or brand name, any company or platform name, "doctor", "clinic", "cure", "heal", "rx", "pharmacy",
  "fda", disease names, "miracle", "guaranteed", or anything that promises a health result.
- Avoid obvious one-word or very common combos that are surely taken; be a little creative so they are likely still free.
- "sub": one short lowercase word for THIS page's subdomain that matches its topic (e.g. memory, focus, energy).
- "why": max 12 words, plain English, why it fits.

PAGE
{page}

Reply with ONLY a JSON array, no other text: [{{"domain":"…com","sub":"…","why":"…"}}, …]"""


def _page_facts(row):
    c = row.get('content') or {}
    h = c.get('header') or {}
    i = row.get('input') or {}
    aud = i.get('audience') or {}
    facts = {'page_name': row.get('name') or row.get('slug'), 'headline': h.get('h1') or c.get('headline') or '',
             'topic_tag': h.get('tag') or '', 'publication': (c.get('publication') or {}).get('name') or '',
             'meta_title': (c.get('meta') or {}).get('title') or '',
             'audience': {k: aud.get(k) for k in ('gender', 'age', 'country', 'notes', 'preset') if aud.get(k)}}
    return json.dumps(facts, ensure_ascii=False)[:1500]


def _ask_claude(row, n=20):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        raise RuntimeError('ANTHROPIC_API_KEY is not set in Vercel')
    body = {'model': os.environ.get('DOMAIN_IDEAS_MODEL') or agent.model(), 'max_tokens': 2000,
            'messages': [{'role': 'user', 'content': PROMPT.format(n=n, page=_page_facts(row))}]}
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=json.dumps(body).encode(), method='POST',
                                 headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Claude said {e.code}: {e.read().decode(errors="replace")[:200]}')
    text = ''.join(b.get('text', '') for b in j.get('content') or [] if b.get('type') == 'text')
    m = re.search(r'\[.*\]', text, re.S)
    out = json.loads(m.group(0)) if m else []
    seen, clean = set(), []
    for x in out if isinstance(out, list) else []:
        d = str((x or {}).get('domain') or '').strip().lower().removeprefix('www.')
        if not NAME_RE.match(d) or d in seen or any(b in d[:-4] for b in BANNED):
            continue
        seen.add(d)
        sub = str(x.get('sub') or '').strip().lower()
        clean.append({'domain': d, 'sub': sub if SUB_RE.match(sub) else 'go', 'why': str(x.get('why') or '').strip()[:120]})
    return clean


def _free(domain):
    """True = not registered, False = taken, None = could not tell."""
    for url in (f'https://rdap.verisign.com/com/v1/domain/{domain}', f'https://rdap.org/domain/{domain}'):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'nutra-domain-ideas', 'Accept': 'application/rdap+json'})
            with urllib.request.urlopen(req, timeout=6):
                return False
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return True
        except Exception:
            pass
    return None


def cached(row):
    return db.kv_data(KV + row['id']) or None


def make(row, user_email=''):
    ideas = _ask_claude(row)
    if not ideas:
        return {'ok': False, 'error': 'Claude did not suggest any usable names. Try again.'}
    old = {x['domain'] for x in (cached(row) or {}).get('ideas') or []}
    ideas = [x for x in ideas if x['domain'] not in old] or ideas
    with ThreadPoolExecutor(max_workers=10) as ex:
        for x, free in zip(ideas, ex.map(lambda x: _free(x['domain']), ideas)):
            x['free'] = free
    good = [x for x in ideas if x['free'] is True][:6]
    if len(good) < 6:
        good += [x for x in ideas if x['free'] is None][:6 - len(good)]
    data = {'ideas': good, 'checked': len(ideas), 'taken': sum(1 for x in ideas if x['free'] is False),
            'at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'by': user_email}
    db.kv_set(KV + row['id'], data)
    return {'ok': True, **data}
