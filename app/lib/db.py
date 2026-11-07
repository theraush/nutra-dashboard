"""Postgres access (Neon on Vercel, any Postgres locally). DATABASE_URL or POSTGRES_URL."""
import os, json
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SCHEMA = """
create table if not exists kv (
  path text primary key, data jsonb not null, version integer not null default 1,
  updated_at timestamptz not null default now());
create table if not exists offers (
  key text primary key, name text not null, offer text, network text default 'jvzoo', ad_account_id text, pixel_id text,
  lander_url text, buy_links jsonb default '[]', product_ids jsonb default '[]', color text, status text default 'active',
  sort integer default 0, budget numeric default 0, start_date date, warn_at integer default 70, auto_pause boolean default true,
  commission_per_sale numeric, autopaused_at timestamptz, warn_alerted_at timestamptz, depleted_alerted_at timestamptz,
  created_at timestamptz default now());
create table if not exists events (
  id bigserial primary key, received_at timestamptz not null default now(), network text default 'jvzoo',
  event text not null, transaction_type text, transaction_id text, product_id text, product_name text,
  product_key text, offer text, pack text, amount numeric, commission numeric, currency text, tid text, fbclid text,
  utm_source text, utm_campaign text, utm_content text, country text, is_test boolean default false, raw jsonb);
create unique index if not exists events_txn_uq on events (network, transaction_id, event, coalesce(transaction_type, ''))
  where transaction_id is not null;
create index if not exists events_day on events (received_at);
create table if not exists notes (id bigserial primary key, day date not null, product text, text text not null,
  created_at timestamptz default now());
create table if not exists budget_events (id bigserial primary key, at timestamptz default now(), product text, event text,
  detail text, amount numeric);
create table if not exists snapshot (id integer primary key, data jsonb not null, at timestamptz default now());
"""

_conn = None


def url():
    u = os.environ.get('DATABASE_URL_UNPOOLED') or os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')  # direct: advisory locks need a session
    if not u:
        raise RuntimeError('No database connected (DATABASE_URL is not set)')
    return u


def conn():
    """One connection per warm function instance; reconnects if it dropped."""
    global _conn
    if _conn is None or _conn.closed or _conn.broken:
        _conn = psycopg.connect(url(), autocommit=True, row_factory=dict_row, prepare_threshold=None)
        _conn.execute(SCHEMA)
    return _conn


def q(sql, args=None):
    with conn().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall() if cur.description else []


def q1(sql, args=None):
    r = q(sql, args)
    return r[0] if r else None


def J(v):
    return Jsonb(v)


# ── kv documents (what the dashboard's Settings tab reads and writes) ──
def kv_get(path):
    return q1('select path, data, version, updated_at from kv where path = %s', (path,))


def kv_list(prefix):
    """Documents directly inside a collection, e.g. prefix 'rules' -> rules/<id>."""
    return q("select path, data, version, updated_at from kv where path like %s and position('/' in substr(path, %s)) = 0 order by path",
             (prefix + '/%', len(prefix) + 2))


def kv_all():
    return q('select path, data, version, updated_at from kv order by path')


def kv_set(path, data, if_version=None):
    """Create or replace. With if_version, only when the stored version still matches (returns None on conflict)."""
    if if_version is None:
        return q1("""insert into kv (path, data) values (%s, %s)
                     on conflict (path) do update set data = excluded.data, version = kv.version + 1, updated_at = now()
                     returning path, version""", (path, J(data)))
    return q1("""update kv set data = %s, version = version + 1, updated_at = now() where path = %s and version = %s
                 returning path, version""", (J(data), path, if_version))


def kv_delete(path):
    q('delete from kv where path = %s', (path,))


def kv_data(path, default=None):
    r = kv_get(path)
    return r['data'] if r else default
