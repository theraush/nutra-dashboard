"""AI page images through OpenAI's image API (OPENAI_API_KEY). Results are saved in the uploads table and
served from /u/<id>.png, like images people upload."""
import os, json, base64, secrets, urllib.request, urllib.error, uuid
from . import db

SIZES = {'landscape': '1536x1024', 'square': '1024x1024', 'portrait': '1024x1536'}


LAST_MODEL = None
LAST_MODEL_OPENAI = None
REALISM = ("\n\nPhoto style (must look like a real, unedited photo, not AI and not stock): candid documentary snapshot, as if taken by a "
           "friend on a recent phone or a 35mm camera; natural, slightly uneven window or room light with real shadows; true-to-life, "
           "slightly muted colours; realistic skin with pores, fine lines, natural age marks and small imperfections that match the "
           "person's age; real, slightly creased everyday clothes; a lived-in, ordinary home or place with normal clutter; natural "
           "depth of field and faint grain; relaxed, unposed body language, eyes not on the camera; correct hands with five fingers. "
           "Avoid: airbrushed or plastic skin, glossy CGI look, perfect symmetry, model looks, stock-photo smiles, studio or HDR "
           "lighting, oversaturated colours, extra or warped fingers, any text, captions, logos or watermarks other than the "
           "product's own label exactly as in the reference.")


class ImageError(Exception):
    pass


def configured():
    return bool(os.environ.get('OPENAI_API_KEY'))


def _post(url, data, headers, timeout=240):
    req = urllib.request.Request(url, data=data, method='POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')[:400]
        try:
            detail = json.loads(detail).get('error', {}).get('message') or detail
        except ValueError:
            pass
        raise ImageError(f'Image API {e.code}: {detail}')
    except urllib.error.URLError as e:
        raise ImageError(f'Image API unreachable: {e.reason}')


FALLBACK_MODELS = ['gpt-image-2.6-sunburst', 'gpt-image-2.6', 'gpt-image-2.5-sunburst', 'gpt-image-2.5', 'gpt-image-2', 'gpt-image-1.5', 'gpt-image-1']


def _rank(mid):
    """Newest version first; 'sunburst' (precise edits, keeps the product label) before 'flare'; plain ids before dated snapshots."""
    import re
    m = re.search(r'image-(\d+(?:\.\d+)?)', mid)
    ver = float(m.group(1)) if m else 0
    return (ver, 'sunburst' in mid, 'flare' not in mid and 'mini' not in mid, not re.search(r'-\d{4}-\d{2}-\d{2}$', mid))


def models(key, fresh=False):
    """Image models this key can use, best first. Cached a day in kv _system/image_models."""
    import datetime
    if os.environ.get('IMAGE_MODEL'):
        return [os.environ['IMAGE_MODEL']]
    cached = db.kv_data('_system/image_models') or {}
    try:
        age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(cached.get('at', ''))).total_seconds()
    except ValueError:
        age = 1e9
    if not fresh and cached.get('ids') and age < 86400:
        return cached['ids']
    ids = []
    try:
        req = urllib.request.Request('https://api.openai.com/v1/models', headers={'Authorization': f'Bearer {key}'})
        with urllib.request.urlopen(req, timeout=20) as r:
            ids = [m['id'] for m in json.loads(r.read()).get('data') or [] if 'image' in m.get('id', '') and m['id'].startswith(('gpt-image', 'chatgpt-image'))]
    except Exception:
        ids = []
    ids = sorted(set(ids), key=_rank, reverse=True) or FALLBACK_MODELS
    db.kv_set('_system/image_models', {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'ids': ids})
    return ids


def _fetch(url, limit=8_000_000):
    """Reference images: our own /u/ uploads come straight from the database; others are downloaded."""
    import re
    m = re.search(r'/u/([A-Za-z0-9_-]{20,40})', url or '')
    if m:
        r = db.q1('select mime, data from uploads where id = %s', (m.group(1),))
        if r:
            return bytes(r['data']), r['mime']
    req = urllib.request.Request(url, headers={'User-Agent': 'nutra-page-builder'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(limit + 1)
        if len(data) > limit:
            raise ImageError('Reference image too big')
        return data, (r.headers.get_content_type() or 'image/png')


def _openai_image(prompt, shape='landscape', refs=None, pre_files=None):
    """-> PNG bytes. pre_files: [(bytes, mime)] sent before the reference images (e.g. a photo to edit)."""
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise ImageError('OPENAI_API_KEY is not set in Vercel, so AI images are off. Use uploaded or vendor images.')
    auth = {'Authorization': f'Bearer {key}'}
    refs = [r for r in (refs or []) if r][:4]
    ref_files = [(i, d, m) for i, (d, m) in enumerate(pre_files or [])]
    for u in refs:
        data, mime = _fetch(u)
        ref_files.append((len(ref_files), data, mime))

    def call(model, size, quality):
        if ref_files:
            boundary = uuid.uuid4().hex
            parts = []
            fields = [('model', model), ('prompt', prompt[:30000]), ('n', '1')] + ([('size', size)] if size else []) + ([('quality', quality)] if quality else [])
            for k, v in fields:
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            for i, data, mime in ref_files:
                ext = {'image/jpeg': 'jpg', 'image/webp': 'webp'}.get(mime, 'png')
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="ref{i}.{ext}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + b'\r\n')
            parts.append(f'--{boundary}--\r\n'.encode())
            return _post('https://api.openai.com/v1/images/edits', b''.join(parts), {**auth, 'Content-Type': f'multipart/form-data; boundary={boundary}'})
        body = {'model': model, 'prompt': prompt[:30000], 'n': 1}
        if size:
            body['size'] = size
        if quality:
            body['quality'] = quality
        return _post('https://api.openai.com/v1/images/generations', json.dumps(body).encode(), {**auth, 'Content-Type': 'application/json'})

    # try the best model this key has; step down when a model is gone, and drop size/quality if a model rejects them
    res, last = None, None
    for attempt, model in enumerate((models(key) + [m for m in FALLBACK_MODELS if m not in models(key)])[:6]):
        size, quality = SIZES.get(shape, SIZES['landscape']), os.environ.get('IMAGE_QUALITY') or 'high'
        for _ in range(3):
            try:
                res = call(model, size, quality)
                break
            except ImageError as e:
                last, low = e, str(e).lower()
                if ' 400' in low and 'size' in low and size:
                    size = 'auto' if size != 'auto' else None
                elif ' 400' in low and 'quality' in low and quality:
                    quality = None
                else:
                    break
        if res is not None:
            global LAST_MODEL_OPENAI
            LAST_MODEL_OPENAI = model
            if attempt:  # remember what works, so the next image goes straight to it
                import datetime
                ids = models(key)
                db.kv_set('_system/image_models', {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'ids': [model] + [i for i in ids if i != model]})
            break
        low = str(last).lower()
        if not ((' 400' in low or ' 404' in low) and ('model' in low or 'does not exist' in low or 'not found' in low or 'deprecated' in low)):
            raise last
    if res is None:
        raise last or ImageError('No image model available for this OpenAI key')
    item = (res.get('data') or [{}])[0]
    if item.get('b64_json'):
        return base64.b64decode(item['b64_json'])
    if item.get('url'):
        return _fetch(item['url'], 20_000_000)[0]
    raise ImageError('Image API returned no image')


# ── Higgsfield (HF_API_KEY_ID + HF_API_KEY_SECRET): SOUL V2, its most realistic people photos ──
HF_ASPECT = {'landscape': '3:2', 'square': '1:1', 'portrait': '2:3'}


def hf_configured():
    return bool(os.environ.get('HF_API_KEY_ID') and os.environ.get('HF_API_KEY_SECRET'))


def _hf_auth(style):
    kid, sec = os.environ.get('HF_API_KEY_ID', '').strip(), os.environ.get('HF_API_KEY_SECRET', '').strip()
    return {'key': {'Authorization': f'Key {kid}:{sec}'},
            'key_swapped': {'Authorization': f'Key {sec}:{kid}'},
            'headers': {'hf-api-key': kid, 'hf-secret': sec},
            'bearer': {'Authorization': f'Bearer {sec}'},
            'bearer_id': {'Authorization': f'Bearer {kid}'}}[style]


def _hf_try(style):
    req = urllib.request.Request('https://api.higgsfield.ai/requests/00000000-0000-0000-0000-000000000000/status', headers=_hf_auth(style))
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')[:300].lower()
        if e.code == 422 and ('authorization' in body or 'header' in body or 'missing' in body):
            return 401  # FastAPI 'field required: authorization' = we were not logged in
        _hf_try.last = body[:160]
        return e.code
    except Exception:
        return 0


def hf_style():
    st = (db.kv_data('_system/hf_auth') or {}).get('style')
    return st or 'key'


def hf_check():
    """Free key check: ask for the status of a request that doesn't exist. 401/403 = bad key. Tries the known login formats."""
    if not hf_configured():
        return {'ok': False, 'why': 'HF_API_KEY_ID / HF_API_KEY_SECRET are not set'}
    tried = {}
    for style in ('key', 'key_swapped', 'headers', 'bearer', 'bearer_id'):
        code = _hf_try(style)
        tried[style] = code
        if code and code not in (401, 403):
            db.kv_set('_system/hf_auth', {'style': style})
            return {'ok': True, 'style': style, 'code': code, 'tried': tried, 'body': getattr(_hf_try, 'last', '')}
    import re as _re
    kid_raw, sec_raw = os.environ.get('HF_API_KEY_ID', ''), os.environ.get('HF_API_KEY_SECRET', '')
    kid, sec = kid_raw.strip(), sec_raw.strip()
    shape = {'id_length': len(kid), 'id_starts': kid[:4], 'id_looks_like_uuid': bool(_re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', kid, _re.I)),
             'id_has_dots': kid.endswith('...') or '…' in kid, 'secret_length': len(sec), 'colon_in_id': ':' in kid, 'colon_in_secret': ':' in sec,
             'spaces_or_newlines_trimmed': kid != kid_raw or sec != sec_raw, 'id_equals_secret': kid == sec}
    return {'ok': False, 'tried': tried, 'why': 'Higgsfield rejected the key in every login format', 'shape': shape}


def _hf_soul(prompt, shape, deadline):
    import time
    auth = {**_hf_auth(hf_style()), 'Content-Type': 'application/json',
            'Idempotency-Key': uuid.uuid4().hex}
    body = {'prompt': prompt[:4000], 'aspect_ratio': HF_ASPECT.get(shape, '3:2'), 'resolution': '1080p', 'batch_size': 1, 'enhance_prompt': False}
    try:
        sub = _post('https://api.higgsfield.ai/higgsfield-ai/soul/v2/standard', json.dumps(body).encode(), auth, timeout=60)
    except ImageError as e:
        if ' 401' in str(e) or ' 403' in str(e):
            raise ImageError('Higgsfield 401: Higgsfield rejected the key (HF_API_KEY_ID / HF_API_KEY_SECRET). Use the ID and secret of the same key, no spaces.')
        if ' 402' in str(e) or 'credit' in str(e).lower():
            raise ImageError('Higgsfield: not enough API credits on the Higgsfield account.')
        raise ImageError('Higgsfield ' + str(e).replace('Image API ', ''))
    status_url = sub.get('status_url') or f"https://api.higgsfield.ai/requests/{sub.get('request_id')}/status"
    wait = 4
    while time.time() < deadline:
        time.sleep(wait)
        wait = min(8, wait + 1)
        req = urllib.request.Request(status_url, headers=_hf_auth(hf_style()))
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                st = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise ImageError(f'Higgsfield {e.code}: {e.read().decode(errors="replace")[:200]}')
        s_ = st.get('status')
        if s_ == 'completed':
            url = ((st.get('images') or [{}])[0] or {}).get('url')
            if not url:
                raise ImageError('Higgsfield returned no image')
            return _fetch(url, 25_000_000)
        if s_ in ('failed', 'nsfw', 'canceled'):
            raise ImageError(f'Higgsfield: {s_} {str(st.get("error") or "")[:150]}')
    raise ImageError('Higgsfield took too long')


PLACE_PRODUCT = ("Edit the FIRST image only: put the product from the SECOND image into the scene so it looks naturally photographed "
                 "there ({where}). Copy the product and its label exactly from the second image, at a realistic size, with matching light, "
                 "shadows and perspective. Keep the person, face, hands, clothes, room, light and framing of the first image exactly as they "
                 "are. No added text.")


def generate(prompt, shape='landscape', refs=None, by='page-builder', engine='openai', where='on the table, within reach'):
    """Saves the image in uploads and returns its id. engine 'higgsfield': SOUL V2 makes the realistic photo, then OpenAI places
    the real product (from refs) into it so the label is right."""
    import time
    global LAST_MODEL
    if str(by).startswith('claude:'):
        prompt = prompt.strip() + REALISM
    if engine == 'higgsfield':
        if not hf_configured():
            raise ImageError('Higgsfield keys (HF_API_KEY_ID, HF_API_KEY_SECRET) are not set in Vercel.')
        data, mime = _hf_soul(prompt, shape, time.time() + 150)
        LAST_MODEL = 'higgsfield soul v2'
        img, out_mime = data, mime
        if refs and os.environ.get('OPENAI_API_KEY'):
            try:
                img = _openai_image(PLACE_PRODUCT.format(where=str(where)[:200]), shape, refs, pre_files=[(data, mime)])
                out_mime = 'image/png'
                LAST_MODEL = f'higgsfield soul v2 + {LAST_MODEL_OPENAI or "openai"} (product placed)'
            except ImageError:
                LAST_MODEL = 'higgsfield soul v2 (product not placed)'
    else:
        img, out_mime = _openai_image(prompt, shape, refs), 'image/png'
        LAST_MODEL = LAST_MODEL_OPENAI
    uid = secrets.token_urlsafe(18)
    db.q('insert into uploads (id, mime, data, bytes, by_email) values (%s, %s, %s, %s, %s)', (uid, out_mime, img, len(img), by))
    return uid
