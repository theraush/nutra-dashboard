"""AI page images through OpenAI's image API (OPENAI_API_KEY). Results are saved in the uploads table and
served from /u/<id>.png, like images people upload."""
import os, json, base64, secrets, urllib.request, urllib.error, uuid
from . import db

SIZES = {'landscape': '1536x1024', 'square': '1024x1024', 'portrait': '1024x1536'}


LAST_MODEL = None


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


def generate(prompt, shape='landscape', refs=None, by='page-builder'):
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise ImageError('OPENAI_API_KEY is not set in Vercel, so AI images are off. Use uploaded or vendor images.')
    auth = {'Authorization': f'Bearer {key}'}
    refs = [r for r in (refs or []) if r][:4]
    ref_files = []
    for i, u in enumerate(refs):
        data, mime = _fetch(u)
        ref_files.append((i, data, mime))

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
            global LAST_MODEL
            LAST_MODEL = model
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
        img = base64.b64decode(item['b64_json'])
    elif item.get('url'):
        img, _ = _fetch(item['url'], 20_000_000)
    else:
        raise ImageError('Image API returned no image')
    uid = secrets.token_urlsafe(18)
    db.q('insert into uploads (id, mime, data, bytes, by_email) values (%s, %s, %s, %s, %s)', (uid, 'image/png', img, len(img), by))
    return uid
