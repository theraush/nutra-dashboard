"""AI page images through OpenAI's image API (OPENAI_API_KEY). Results are saved in the uploads table and
served from /u/<id>.png, like images people upload."""
import os, json, base64, secrets, urllib.request, urllib.error, uuid
from . import db

SIZES = {'landscape': '1536x1024', 'square': '1024x1024', 'portrait': '1024x1536'}


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
    size = SIZES.get(shape, SIZES['landscape'])
    model = os.environ.get('IMAGE_MODEL') or 'gpt-image-1'
    quality = os.environ.get('IMAGE_QUALITY') or 'high'
    auth = {'Authorization': f'Bearer {key}'}
    refs = [r for r in (refs or []) if r][:4]
    if refs:
        boundary = uuid.uuid4().hex
        parts = []
        def field(name, value):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        for k, v in (('model', model), ('prompt', prompt[:30000]), ('size', size), ('quality', quality), ('n', '1')):
            field(k, v)
        for i, u in enumerate(refs):
            data, mime = _fetch(u)
            ext = {'image/jpeg': 'jpg', 'image/webp': 'webp'}.get(mime, 'png')
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="ref{i}.{ext}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        res = _post('https://api.openai.com/v1/images/edits', b''.join(parts), {**auth, 'Content-Type': f'multipart/form-data; boundary={boundary}'})
    else:
        res = _post('https://api.openai.com/v1/images/generations',
                    json.dumps({'model': model, 'prompt': prompt[:30000], 'size': size, 'quality': quality, 'n': 1}).encode(),
                    {**auth, 'Content-Type': 'application/json'})
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
