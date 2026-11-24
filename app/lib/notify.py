"""Alerts to the phone: Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) and/or email via Resend
(RESEND_API_KEY + ALERT_EMAIL [+ ALERT_FROM]). Whatever is configured gets the message."""
import os, json, urllib.request


def _post(url, body, headers=None):
    import urllib.error
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'nutra-dashboard', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')[:300]
        try:
            detail = json.loads(detail).get('message') or detail
        except ValueError:
            pass
        raise RuntimeError(f'{e.code}: {detail}')


def configured():
    return bool((os.environ.get('TELEGRAM_BOT_TOKEN') and os.environ.get('TELEGRAM_CHAT_ID'))
                or (os.environ.get('RESEND_API_KEY') and os.environ.get('ALERT_EMAIL')))


def send(text, subject='NUTRA alert'):
    """Returns a list of error strings (empty when everything that is configured worked)."""
    errs = []
    tg, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if tg and chat:
        try:
            _post(f'https://api.telegram.org/bot{tg}/sendMessage', {'chat_id': chat, 'text': text[:4000], 'disable_web_page_preview': True})
        except Exception as e:
            errs.append(f'Telegram: {e}')
    key, to = os.environ.get('RESEND_API_KEY'), os.environ.get('ALERT_EMAIL')
    if key and to:
        try:
            _post('https://api.resend.com/emails', {
                'from': os.environ.get('ALERT_FROM') or 'NUTRA <onboarding@resend.dev>',
                'to': [x.strip() for x in to.split(',') if x.strip()], 'subject': subject, 'text': text},
                {'Authorization': f'Bearer {key}'})
        except Exception as e:
            errs.append(f'Email: {e}')
    return errs


def email_configured():
    return bool(os.environ.get('RESEND_API_KEY'))


def send_email(to, subject, text, html_body=None):
    """One email to one person (password resets). Raises on failure."""
    key = os.environ.get('RESEND_API_KEY')
    if not key:
        raise RuntimeError('RESEND_API_KEY is not set')
    body = {'from': os.environ.get('MAIL_FROM') or os.environ.get('ALERT_FROM') or 'NUTRA <onboarding@resend.dev>',
            'to': [to], 'subject': subject, 'text': text}
    if html_body:
        body['html'] = html_body
    _post('https://api.resend.com/emails', body, {'Authorization': f'Bearer {key}'})
