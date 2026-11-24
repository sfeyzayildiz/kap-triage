"""Collect daily price bars from Matriks into DuckDB (table daily_bars).

Two steps, so a parse fix never needs a second pull:
  --pull  one request per symbol to v1/tick/bar.gz, raw JSON saved to data/raw_bars/
  --load  parse data/raw_bars/ into daily_bars (no network)

Permission: Matriks approved daily bars by email on 2026-11-02 (one pull, max 1 request/sec).
Prices are unadjusted (the API allows only divide=false), so splits and bonus issues
show up as jumps; --load counts them, it does not fix them.
Stdout shows only counts and dates, never prices.

Usage:
  python -m kap_triage.collect.prices --plan
  python -m kap_triage.collect.prices --pull --yes
  python -m kap_triage.collect.prices --load
"""

import argparse
import gzip
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

import duckdb
from kap_triage.settings import settings

API = 'https://<MATRIKS_API_HOST>/dumrul'
DB_PATH = settings.path('kap.duckdb')
RAW_DIR = settings.path('raw_bars')
MANIFEST = f'{RAW_DIR}/_manifest.jsonl'
INDEX = 'XU100'
MIN_INTERVAL = 1.1
MAX_TRIES = 5
COUNT_MAX = 1000
LEAD_DAYS = 60
JUMP = 0.3
FIELDS = ('open', 'high', 'low', 'close', 'volume', 'totalQuantity', 'weightedAverage')

SCHEMA = """CREATE TABLE IF NOT EXISTS daily_bars (
    symbol VARCHAR, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    volume DOUBLE, total_quantity DOUBLE, weighted_average DOUBLE, time_ms BIGINT,
    PRIMARY KEY (symbol, date))"""


class StopPull(Exception):
    pass


def in_collection_window(now):
    """The nightly collector writes to the DB around 23:43; keep a wide margin."""
    return now.hour == 23 and now.minute >= 30


def decode(content):
    """Response body to a list of bars. The path ends in .gz, so accept gzip or plain JSON."""
    if content[:2] == b'\x1f\x8b':
        content = gzip.decompress(content)
    data = json.loads(content)
    if not isinstance(data, list):
        raise ValueError('unexpected_format')
    return data


def parse_bars(sym, bars):
    """Rows for daily_bars; bars without a date or a positive close are dropped."""
    rows = []
    for b in bars:
        close = b.get('close')
        if not b.get('date') or not isinstance(close, (int, float)) or close <= 0:
            continue
        rows.append((sym, date.fromisoformat(b['date']), *(b.get(f) for f in FIELDS), b.get('time')))
    return rows


def count_jumps(rows):
    """Day-to-day close moves above JUMP; with unadjusted prices these may be splits."""
    jumps = 0
    rows = sorted(rows, key=lambda r: r[1])
    for prev, cur in zip(rows, rows[1:]):
        if abs(cur[5] / prev[5] - 1) > JUMP:
            jumps += 1
    return jumps


def load_symbols():
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        syms = [
            r[0]
            for r in con.execute(
                'SELECT DISTINCT symbol FROM disclosures WHERE symbol IS NOT NULL ORDER BY 1'
            ).fetchall()
        ]
        first = con.execute('SELECT min(CAST(published_at AS DATE)) FROM disclosures').fetchall()[0][0]
    finally:
        con.close()
    return syms + [INDEX], first - timedelta(days=LEAD_DAYS)


def done_symbols(manifest, end):
    """Symbols already pulled OK up to this end date. A refresh with a later end pulls them again
    (until 2026-11-09 any earlier OK counted, so a refresh would have pulled only the failed symbols)."""
    return {m['symbol'] for m in manifest if m['status'] == 'ok' and m.get('end') == end.isoformat()}


def read_manifest():
    if not os.path.exists(MANIFEST):
        return []
    with open(MANIFEST) as f:
        return [json.loads(l) for l in f if l.strip()]


def pull(symbols, start, end):
    import requests
    from dotenv import load_dotenv

    load_dotenv()
    headers = {'Authorization': f'jwt {os.environ["KAP_TOKEN"]}'}
    os.makedirs(RAW_DIR, exist_ok=True)
    from kap_triage.collect.pull_guard import AlreadyPulled, claim

    try:
        claim('prices', resume=True)  # one pull per day; a re-run after a failure resumes the same session
    except AlreadyPulled as e:
        raise StopPull(str(e))
    done = done_symbols(read_manifest(), end)
    todo = [s for s in symbols if s not in done]
    print(f'symbols={len(symbols)} already_ok={len(done & set(symbols))} to_pull={len(todo)}')
    stats = {'ok': 0, 'empty': 0, 'http_error': 0, 'bad_format': 0, 'truncated': 0}
    with open(MANIFEST, 'a') as man:
        for i, sym in enumerate(todo, 1):
            params = {'symbol': sym, 'period': '1day', 'start': start.isoformat(), 'end': end.isoformat()}
            status, n, wait = None, 0, MIN_INTERVAL
            for attempt in range(1, MAX_TRIES + 1):
                time.sleep(wait)
                resp = requests.get(f'{API}/v1/tick/bar.gz', params=params, headers=headers, timeout=60)
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = MIN_INTERVAL * 2**attempt
                    continue
                break
            if resp.status_code in (401, 403):
                raise StopPull(f'HTTP {resp.status_code}: token problem, stopped after {i - 1} symbols')
            if resp.status_code != 200:
                status = f'http_{resp.status_code}'
                stats['http_error'] += 1
            else:
                try:
                    bars = decode(resp.content)
                except ValueError:
                    status = 'bad_format'
                    stats['bad_format'] += 1
                else:
                    with open(f'{RAW_DIR}/{sym}.json', 'w') as f:
                        json.dump(bars, f)
                    n = len(bars)
                    status = 'ok' if n else 'empty'
                    stats['ok' if n else 'empty'] += 1
                    stats['truncated'] += n >= COUNT_MAX
            man.write(
                json.dumps(
                    {
                        'symbol': sym,
                        'status': status,
                        'n_bars': n,
                        'start': start.isoformat(),
                        'end': end.isoformat(),
                        'fetched_at': datetime.now().isoformat(timespec='seconds'),
                    }
                )
                + '\n'
            )
            man.flush()
            if i % 25 == 0:
                print(f'  {i}/{len(todo)}')
    print(' '.join(f'{k}={v}' for k, v in stats.items()))


def load():
    files = sorted(f for f in os.listdir(RAW_DIR) if f.endswith('.json'))
    con = duckdb.connect(DB_PATH)
    try:
        con.execute(SCHEMA)
        total = dropped = jumps = empty = 0
        for name in files:
            sym = name[:-5]
            with open(f'{RAW_DIR}/{name}') as f:
                bars = json.load(f)
            rows = parse_bars(sym, bars)
            dropped += len(bars) - len(rows)
            if not rows:
                empty += 1
                continue
            jumps += count_jumps(rows)
            con.executemany('INSERT OR REPLACE INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
            total += len(rows)
        summary = con.execute('SELECT count(DISTINCT symbol),count(*),min(date),max(date) FROM daily_bars').fetchall()[
            0
        ]
    finally:
        con.close()
    print(
        f'files={len(files)} loaded_rows={total} dropped_rows={dropped} empty_symbols={empty} jumps_over_{int(JUMP * 100)}pct={jumps}'
    )
    print(f'daily_bars: symbols={summary[0]} rows={summary[1]} first={summary[2]} last={summary[3]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', action='store_true', help='show what a pull would do, no network')
    ap.add_argument('--pull', action='store_true', help='one request per symbol (Matriks)')
    ap.add_argument('--yes', action='store_true', help='confirm the pull')
    ap.add_argument('--load', action='store_true', help='parse raw files into daily_bars, no network')
    args = ap.parse_args()
    if not (args.plan or args.pull or args.load):
        ap.error('give --plan, --pull or --load')
    if in_collection_window(datetime.now()):
        sys.exit('nightly collection window (23:30-23:59), try later')

    if args.plan or args.pull:
        symbols, start = load_symbols()
        end = date.today() - timedelta(days=1)
        print(
            f'symbols={len(symbols)} (incl. {INDEX}) start={start} end={end} '
            f'requests<={len(symbols)} est_minutes={len(symbols) * MIN_INTERVAL / 60:.1f}'
        )
        if args.pull:
            if not args.yes:
                sys.exit("add --yes to pull; this is the day's price pull")
            try:
                pull(symbols, start, end)
            except StopPull as e:
                sys.exit(str(e))
    if args.load:
        load()


if __name__ == '__main__':
    main()
