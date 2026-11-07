"""Alerts to the phone: Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) and/or email via Resend
(RESEND_API_KEY + ALERT_EMAIL [+ ALERT_FROM]). Whatever is configured gets the message."""
import os, json, urllib.request


def _post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


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
