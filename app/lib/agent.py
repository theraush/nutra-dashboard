"""Claude Managed Agents (beta) over plain HTTPS. The dashboard starts one session per page build; the agent
works in Anthropic's cloud and reports back to /api/agent/<page>/... with a per-page token."""
import os, json, hashlib, urllib.request, urllib.error
from . import db

API = 'https://api.anthropic.com/v1'
BETA = 'managed-agents-2026-04-01'
AGENT_VERSION = 3  # bump when the system prompt or tools change, so the stored agent is updated


class AgentError(Exception):
    pass


def configured():
    return bool(os.environ.get('ANTHROPIC_API_KEY'))


def call(method, path, body=None, timeout=60):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        raise AgentError('ANTHROPIC_API_KEY is not set in Vercel')
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        'x-api-key': key, 'anthropic-version': '2023-06-01', 'anthropic-beta': BETA, 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')[:500]
        try:
            detail = json.loads(detail).get('error', {}).get('message') or detail
        except ValueError:
            pass
        raise AgentError(f'Anthropic API {e.code}: {detail}')
    except urllib.error.URLError as e:
        raise AgentError(f'Anthropic API unreachable: {e.reason}')


def model():
    return os.environ.get('PAGE_AGENT_MODEL') or 'claude-sonnet-5-5'


def ensure(system_prompt):
    """Create (once) the page-builder agent and its cloud environment; ids are kept in kv _system/page_agent."""
    st = db.kv_data('_system/page_agent') or {}
    want = {'version': AGENT_VERSION, 'model': model(), 'prompt_hash': hashlib.sha256(system_prompt.encode()).hexdigest()[:16]}
    if not st.get('environment_id'):
        env = call('POST', '/environments', {'name': 'nutra-page-builder', 'config': {'type': 'cloud', 'networking': {'type': 'unrestricted'}}})
        st['environment_id'] = env['id']
    body = {'name': 'NUTRA page builder', 'model': {'id': want['model']}, 'system': system_prompt,
            'tools': [{'type': 'agent_toolset_20260401', 'default_config': {'permission_policy': {'type': 'always_allow'}}}],
            'metadata': {'app': 'nutra-dashboard'}}
    if not st.get('agent_id'):
        st['agent_id'] = call('POST', '/agents', body)['id']
    elif any(st.get(k) != v for k, v in want.items()):
        try:
            call('POST', f"/agents/{st['agent_id']}", body)
        except AgentError:
            st['agent_id'] = call('POST', '/agents', body)['id']
    st.update(want)
    db.kv_set('_system/page_agent', st)
    return st


def start_session(system_prompt, title, text, page_id, budget_cents=None):
    st = ensure(system_prompt)
    body = {'agent': st['agent_id'], 'environment_id': st['environment_id'], 'title': title[:480],
            'metadata': {'page_id': page_id},
            'initial_events': [{'type': 'user.message', 'content': [{'type': 'text', 'text': text}]}]}
    cents = budget_cents or int(os.environ.get('PAGE_BUDGET_CENTS') or 1000)
    body['budget'] = {'type': 'limit', 'max_list_cost': {'amount': str(cents), 'currency': 'USD'}}
    try:
        return call('POST', '/sessions', body)
    except AgentError as e:
        if 'budget' in str(e).lower():  # budgets need list-priced models; run uncapped rather than fail
            body.pop('budget', None)
            return call('POST', '/sessions', body)
        raise


def send(session_id, text):
    return call('POST', f'/sessions/{session_id}/events', {'events': [{'type': 'user.message', 'content': [{'type': 'text', 'text': text}]}]})


def session(session_id):
    return call('GET', f'/sessions/{session_id}', timeout=20)


def last_words(session_id):
    """The agent's latest message text (to explain a stop), or ''."""
    try:
        ev = call('GET', f'/sessions/{session_id}/events?limit=50&order=desc', timeout=20)
    except AgentError:
        return ''
    for e in ev.get('data') or []:
        if e.get('type') == 'agent.message':
            parts = [b.get('text', '') for b in e.get('content') or [] if b.get('type') == 'text']
            if any(parts):
                return ' '.join(parts)[:600]
        if e.get('type') == 'session.error':
            return str(e.get('error') or e)[:600]
    return ''


def stop(session_id):
    try:
        call('POST', f'/sessions/{session_id}/events', {'events': [{'type': 'user.interrupt'}]}, timeout=20)
    except AgentError:
        pass
