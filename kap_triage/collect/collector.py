"""Collect KAP "Yeni Is Iliskisi" data from Matriks into DuckDB.

Two sources, joined later by KAP link:
  1) new-business-api  -> table new_business (amount, currency, ratios)
  2) news search (source:KAP tag:NewBusiness) -> table disclosures (form + free text)

Matriks rules: max 1 request/sec (1.1 s wait + backoff), raw data stays in data/.

Usage:
  python -m kap_triage.collect.collector --start 2026-09-01 --end 2026-09-30"""

from zoneinfo import ZoneInfo
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import date, datetime, timedelta
from enum import IntEnum
from math import isfinite
from urllib.parse import urlsplit
import duckdb
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup

from kap_triage.collect.pull_guard import AlreadyPulled, claim
from kap_triage.settings import settings


# --- Matriks collection ---------------------------------------------------------

# new_business comes from prod (probe v2, 2026-11-05: same deals, newer revenue periods);
# news is not tested on prod yet, so it stays on apitest
NB_API = os.environ.get('MATRIKS_NB_API', 'https://<MATRIKS_API_HOST>/dumrul')
NEWS_API = os.environ.get('MATRIKS_NEWS_API', 'https://<MATRIKS_API_HOST>/dumrul')
DB_PATH = settings.path('kap.duckdb')
SCHEMA_PATH = str(Path(__file__).with_name('schema.sql'))
MIN_INTERVAL = 1.1
MAX_TRIES = 5
PAGE_SIZE = 100
SEARCH_COUNT = 2000

load_dotenv()
KAP_LINK = re.compile(r'https?://www\.kap\.org\.tr/Bildirim/\d+')
HEADLINE_SYM = re.compile(r'KAP:\s*([A-Z0-9]+)')


class CollectionStatus(IntEnum):
    OK = 0
    FAILED = 1
    PARTIAL = 3


# This exit code is reserved for a lock failure before claim() and any vendor request.
PRE_PULL_LOCK = 4


def token():
    """The Matriks token from .env, read when a request is made: importing this module needs no token."""
    value = os.environ.get('KAP_TOKEN')
    if not value:
        raise RuntimeError('KAP_TOKEN is missing: put it in .env (never commit it)')
    return value


def get(path, params, base=NEWS_API):
    wait = MIN_INTERVAL
    for attempt in range(1, MAX_TRIES + 1):
        time.sleep(wait)
        resp = requests.get(f'{base}/{path}', params=params, headers={'Authorization': f'jwt {token()}'}, timeout=60)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = MIN_INTERVAL * 2**attempt
            print(f'  HTTP {resp.status_code}, retry {attempt}/{MAX_TRIES} in {wait:.1f}s')
            continue
        if resp.status_code != 200:
            raise RuntimeError(f'HTTP {resp.status_code} on {path}')
        return resp.json()
    raise RuntimeError(f'Gave up on {path} after repeated 429/5xx.')


def month_ranges(start, end):
    s = start
    while s <= end:
        next_month = (s.replace(day=1) + timedelta(days=32)).replace(day=1)
        e = min(next_month - timedelta(days=1), end)
        yield s, e
        s = e + timedelta(days=1)


def norm_url(url):
    base, *suffix = re.split(r'([?#])', (url or '').strip(), maxsplit=1)
    url = base.rstrip('/') + ''.join(suffix)
    return f'https://{url[7:]}' if url.startswith('http://') else url


def answer_is_yes(value):
    return (value or '').strip().lower().startswith('evet')


def has_value(value):
    return bool(value.strip()) if isinstance(value, str) else value is not None


def loses_value(previous, incoming):
    return has_value(previous) and not has_value(incoming)


def finite_number(value):
    try:
        return value is None or isfinite(float(value))
    except (ValueError, OverflowError):
        return False


def fetch_new_business(con, s, e, base=NB_API):
    rows = get('v1/new-business-api', {'start': s.isoformat(), 'end': e.isoformat()}, base=base)
    if not isinstance(rows, list):
        raise ValueError('Invalid new_business response')
    saved, invalid = 0, 0
    numeric = ('amount', 'per', 'rt', 'shfRet', 'tcmbExRt', 'cumRt', 'marValRt')
    fields = ('sym', 'date', 'cur', 'amount', 'desc', *numeric[1:])
    for row in rows:
        url = row.get('url') if isinstance(row, dict) else None
        if not isinstance(url, str) or any(char.isspace() or not char.isprintable() for char in url.strip()):
            invalid += 1
            continue
        url = norm_url(url)
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            invalid += 1
            continue
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or port == 0:
            invalid += 1
            continue
        if not all(field in row for field in fields):
            invalid += 1
            continue
        values = tuple(row[field] for field in fields)
        if any(value is not None and type(value) not in (str, int, float) for value in values):
            invalid += 1
            continue
        if not all(finite_number(row[field]) for field in numeric):
            invalid += 1
            continue
        previous = con.execute(
            """SELECT sym,date,cur,amount,description,per,rt,shf_ret,tcmb_ex_rt,cum_rt,mar_val_rt
            FROM new_business WHERE url = ?""",
            (url,),
        ).fetchone()
        # The available vendor contract does not establish that null clears a stored value.
        if not any(map(has_value, values)) or (
            previous is not None and any(loses_value(old, new) for old, new in zip(previous, values))
        ):
            invalid += 1
            continue
        try:
            con.execute(
                """INSERT OR REPLACE INTO new_business
                (url,sym,date,cur,amount,description,per,rt,shf_ret,tcmb_ex_rt,cum_rt,mar_val_rt)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (url, *values),
            )
        except duckdb.DataError:
            invalid += 1
            continue
        saved += 1
    return saved, invalid


def fetch_disclosures(con, s, e):
    query = f'source:KAP tag:NewBusiness after:{s.isoformat()} before:{(e + timedelta(days=1)).isoformat()}'
    saved, out_range = 0, 0
    seen = set()
    try:
        search = get('v2/news/search', {'query': query, 'count': SEARCH_COUNT})
        if not isinstance(search, dict) or search.get('err'):
            raise ValueError('Search returned an error or invalid response')
        qid, total = search.get('id'), search.get('messageCount')
        if not valid_id(qid) or type(total) is not int or total < 0:
            raise ValueError('Search response lacks a valid query ID or messageCount')
        limit = min(total, SEARCH_COUNT)
        for page, offset in enumerate(range(0, limit, PAGE_SIZE)):
            items = get('v2/news/search/page', {'qid': qid, 'page': page, 'pageSize': PAGE_SIZE})
            if not isinstance(items, list):
                raise ValueError('Invalid search page response')
            unique = []
            for item in items:
                if isinstance(item, dict) and valid_id(item.get('id')):
                    key = str(item['id'])
                    if key not in seen:
                        seen.add(key)
                        unique.append(item)
            # Write each usable page before requesting the next one.
            written, ignored, invalid = save_disclosures(con, s, e, unique)
            saved += written
            out_range += ignored
            if len(unique) != len(items) or len(items) != min(PAGE_SIZE, total - offset):
                raise ValueError('Search page has an unexpected count, missing ID or repeated ID')
            if invalid:
                raise ValueError('Search page contains invalid disclosure rows')
        if total >= SEARCH_COUNT:
            raise ValueError('Search cap reached')
    except Exception as exc:
        print(f'  disclosures incomplete: {exc}', file=sys.stderr)
        status = CollectionStatus.PARTIAL if saved or out_range else CollectionStatus.FAILED
        return status, saved, out_range
    return CollectionStatus.OK, saved, out_range


def valid_id(value):
    if isinstance(value, str):
        return bool(value) and value.isprintable() and not any(char.isspace() for char in value)
    return type(value) is int and value > 0


def save_disclosures(con, s, e, items):
    if not items:
        return 0, 0, 0
    existing = {
        row[0]: row[1:]
        for row in con.execute(
            """SELECT news_id,kap_url,headline,symbol,aciklama,form_json,is_update,is_correction
            FROM disclosures WHERE news_id IN (SELECT unnest(?))""",
            ([str(item['id']) for item in items],),
        ).fetchall()
    }
    out_range, invalid = 0, 0
    data = []
    for item in items:
        stamp = item.get('date')
        try:
            published = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(ZoneInfo('Europe/Istanbul'))
        except (AttributeError, ValueError, OverflowError):
            invalid += 1
            continue
        if not s <= published.date() <= e:
            out_range += 1
            continue
        content = item.get('content')
        if not isinstance(content, str) or not content.strip():
            invalid += 1
            continue
        link = KAP_LINK.search(content)
        syms = item.get('symbol') or []
        headline = item.get('headline')
        if (headline is not None and not isinstance(headline, str)) or (
            not isinstance(syms, list) or (syms and not isinstance(syms[0], str))
        ):
            invalid += 1
            continue
        sym = syms[0] if syms else (HEADLINE_SYM.search(headline or '') or [None, None])[1]
        form = parse_form(content)
        if not any(form.values()):
            invalid += 1
            continue
        url = norm_url(link.group(0) if link else None)
        description = form.get('Açıklama')
        update = 'Yapılan Açıklama Güncelleme mi?'
        correction = 'Yapılan Açıklama Düzeltme mi?'
        previous = existing.get(str(item['id']))
        if previous is not None:
            old_url, old_headline, old_symbol, old_description, old_form, old_update, old_correction = previous
            try:
                old_fields = json.loads(old_form or '{}')
            except ValueError:
                invalid += 1
                continue
            if not isinstance(old_fields, dict):
                invalid += 1
                continue
            old_values = old_url, old_headline, old_symbol, old_description
            new_values = url, headline, sym, description
            if (
                any(loses_value(old, new) for old, new in zip(old_values, new_values))
                or any(loses_value(value, form.get(key)) for key, value in old_fields.items())
                or (old_update and not form.get(update))
                or (old_correction and not form.get(correction))
            ):
                invalid += 1
                continue
        data.append(
            (
                str(item['id']),
                url,
                headline,
                sym,
                published.replace(tzinfo=None),
                answer_is_yes(form.get(update)),
                answer_is_yes(form.get(correction)),
                json.dumps(form, ensure_ascii=False),
                description,
            )
        )
    if data:
        con.executemany(
            """INSERT OR REPLACE INTO disclosures
            (news_id,kap_url,headline,symbol,published_at,is_update,is_correction,form_json,aciklama)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            data,
        )
    return len(data), out_range, invalid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True, type=date.fromisoformat)
    parser.add_argument('--end', required=True, type=date.fromisoformat)
    args = parser.parse_args()
    if args.start > args.end:
        parser.error('--start must be on or before --end')

    try:
        con = duckdb.connect(DB_PATH)
    except duckdb.IOException as exc:
        if 'could not set lock' not in str(exc).lower():
            raise
        print(exc, file=sys.stderr)
        return PRE_PULL_LOCK
    with con:
        con.execute(Path(SCHEMA_PATH).read_text(encoding='utf-8'))
        try:
            claim('collector')  # after the DB lock, right before the first request
        except AlreadyPulled as exc:
            print(exc, file=sys.stderr)
            return CollectionStatus.FAILED

        progress = False
        for s, e in month_ranges(args.start, args.end):
            print(f'{s} -> {e}')
            try:
                nb, invalid_nb = fetch_new_business(con, s, e)
            except Exception as exc:
                print(f'  new_business incomplete: {exc}', file=sys.stderr)
                return CollectionStatus.PARTIAL if progress else CollectionStatus.FAILED
            status, dc, out = fetch_disclosures(con, s, e)
            print(f'  new_business: {nb} | disclosures: {dc} (ignored out of range: {out})')
            if invalid_nb:
                print(f'  new_business incomplete: {invalid_nb} invalid rows', file=sys.stderr)
            if invalid_nb or status != CollectionStatus.OK:
                return CollectionStatus.PARTIAL if progress or nb or dc or out else CollectionStatus.FAILED
            progress = True

        nb_total = con.execute('SELECT count(*) FROM new_business').fetchall()[0][0]
        dc_total = con.execute('SELECT count(*) FROM disclosures').fetchall()[0][0]
        matched = con.execute("""SELECT count(*) FROM new_business n
            JOIN disclosures d ON n.url=d.kap_url""").fetchall()[0][0]
        print(f'\nTotals -> new_business: {nb_total} | disclosures: {dc_total} | matched by KAP link: {matched}')
    return CollectionStatus.OK


# --- KAP form table -> dict -----------------------------------------------------


def parse_form(content):
    soup = BeautifulSoup(content or '', 'html.parser')
    form = {}
    for row in soup.find_all('tr'):
        tds = row.find_all('td')
        if len(tds) != 2:
            continue
        key = tds[0].get_text(' ', strip=True)
        if not key:
            continue
        value = tds[1].get_text(' ', strip=True)
        form[key] = value
    return form


if __name__ == '__main__':
    sys.exit(main())
