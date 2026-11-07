"""Meta Marketing API (Graph API) calls with a system-user token in META_TOKEN."""
import os, json, time, urllib.request, urllib.parse, urllib.error, datetime

VER = os.environ.get('META_API_VERSION', 'v21.0')
BASE = f'https://graph.facebook.com/{VER}/'


class MetaError(Exception):
    pass


def token():
    t = os.environ.get('META_TOKEN')
    if not t:
        raise MetaError('META_TOKEN is not set')
    return t


def _call(method, path, params=None, tries=3):
    params = dict(params or {})
    params['access_token'] = token()
    url = path if path.startswith('http') else BASE + path
    data = None
    if method == 'GET':
        if not path.startswith('http'):
            url += '?' + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    for i in range(tries):
        req = urllib.request.Request(url, data=data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors='replace')
            try:
                err = json.loads(body).get('error', {})
            except ValueError:
                err = {'message': body[:200]}
            if e.code >= 500 or err.get('code') in (1, 2, 4, 17, 341, 613):  # transient / rate limit
                if i < tries - 1:
                    time.sleep(2 * (i + 1))
                    continue
            raise MetaError(f"{err.get('message') or e.reason} (code {err.get('code')})")
        except urllib.error.URLError as e:
            if i < tries - 1:
                time.sleep(2)
                continue
            raise MetaError(str(e.reason))


def _pages(path, params):
    out, res = [], _call('GET', path, params)
    while True:
        out += res.get('data', [])
        nxt = (res.get('paging') or {}).get('next')
        if not nxt:
            return out
        res = _call('GET', nxt)


def _lpv(row):
    for a in row.get('actions') or []:
        if a.get('action_type') == 'landing_page_view':
            return int(float(a.get('value') or 0))
    return 0


def act(acct):
    a = str(acct)
    return a if a.startswith('act_') else 'act_' + a


def account_daily(acct, since, until):
    rows = _pages(f'{act(acct)}/insights', {
        'level': 'account', 'time_increment': 1, 'limit': 500,
        'time_range': json.dumps({'since': since, 'until': until}),
        'fields': 'spend,impressions,inline_link_clicks,actions'})
    return [{'date': r['date_start'], 'spend': float(r.get('spend') or 0), 'impr': int(r.get('impressions') or 0),
             'clicks': int(r.get('inline_link_clicks') or 0), 'lpv': _lpv(r)} for r in rows]


def ads_daily(acct, since, until):
    rows = _pages(f'{act(acct)}/insights', {
        'level': 'ad', 'time_increment': 1, 'limit': 500,
        'time_range': json.dumps({'since': since, 'until': until}),
        'fields': 'ad_id,ad_name,campaign_name,adset_name,spend,impressions,inline_link_clicks,actions'})
    status = {a['id']: a.get('effective_status') for a in _pages(f'{act(acct)}/ads', {'fields': 'id,effective_status', 'limit': 500})}
    return [{'id': r['ad_id'], 'name': r.get('ad_name'), 'campaign': r.get('campaign_name'), 'adset': r.get('adset_name'),
             'status': status.get(r['ad_id'], ''), 'date': r['date_start'], 'spend': float(r.get('spend') or 0),
             'impr': int(r.get('impressions') or 0), 'clicks': int(r.get('inline_link_clicks') or 0), 'lpv': _lpv(r)} for r in rows]


def first_pixel(acct):
    px = _call('GET', f'{act(acct)}/adspixels', {'fields': 'id', 'limit': 5}).get('data') or []
    return px[0]['id'] if px else None


def add_to_cart_daily(pixel_id, since):
    """JVZoo reports each order-form visit to the offer's pixel as AddToCart."""
    start = int(datetime.datetime.fromisoformat(since + 'T00:00:00+00:00').timestamp())
    res = _pages(f'{pixel_id}/stats', {'aggregation': 'event', 'start_time': start})
    days = {}
    for slot in res:
        d = str(slot.get('start_time', ''))[:10]
        for x in slot.get('data') or []:
            if x.get('value') == 'AddToCart':
                days[d] = days.get(d, 0) + int(x.get('count') or 0)
    return [{'date': d, 'n': n} for d, n in sorted(days.items())]


def active_campaigns(acct):
    return [c for c in _pages(f'{act(acct)}/campaigns', {'fields': 'id,name,effective_status', 'limit': 500})
            if c.get('effective_status') == 'ACTIVE']


def pause(entity_id):
    """The only change this app ever makes in Meta."""
    r = _call('POST', str(entity_id), {'status': 'PAUSED'}, tries=2)
    if not r.get('success', True):
        raise MetaError(f'pause of {entity_id} not confirmed')
