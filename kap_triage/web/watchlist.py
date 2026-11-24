"""Watchlist module: keeps the analyst's tracked tickers in data/watchlist.json.

Data contract:
- Plain JSON list of uppercase ASCII tickers (e.g. ["SVN1", "BLS2"]), no dates.
- Validation order: strip -> reject Turkish letters -> ASCII check -> uppercase -> 3-6 ASCII alphanumeric.
- Max 50 tickers (analyst scope and abuse limit); full list is rejected explicitly.
- Missing file returns an empty list; broken file (invalid JSON, bad item or duplicate) is never overwritten and blocks writes.
- Duplicate add returns 'exists'; removing a missing ticker passes silently (returns 'absent').

Usage:
"""

import json
import os
import re
import threading
from kap_triage.settings import settings

PATH = settings.path('watchlist.json')
MAX = 50
CODE_RE = re.compile(r'[A-Z0-9]{3,6}')
TR_CHARS = set('çğıöşüÇĞİÖŞÜ')
LOCK = threading.Lock()
# 'absent' has no entry here on purpose: removing a missing ticker passes silently
MESSAGES = {
    'added': 'Takip listesine eklendi.',
    'removed': 'Takip listesinden çıkarıldı.',
    'exists': 'Bu şirket zaten takip listesinde.',
    'full': f'En fazla {MAX} şirket takip edilebilir.',
    'turkish': 'Türkçe karakter kullanmayın, ör. SISE, BIMAS.',
    'bad_code': 'Hisse kodu 3-6 karakter harf veya rakam olmalı (desene uymuyor).',
    'broken': f'Takip listesi dosyası bozuk ({os.path.basename(PATH)}); ekleme/çıkarma kapalı. Dosyayı silin ya da düzeltin.',
}


def normalize(raw):
    """Clean and validate a ticker; returns (code, None) or (None, status_code)."""
    s = (raw or '').strip()
    if any(c in TR_CHARS for c in s):
        return None, 'turkish'
    if not s.isascii():
        return None, 'bad_code'
    code = s.upper()
    if not CODE_RE.fullmatch(code):
        return None, 'bad_code'
    return code, None


def load(path=PATH):
    """Return (codes, broken). Missing file is ([], False); invalid JSON, bad items or duplicates are ([], True)."""
    if not os.path.exists(path):
        return [], False
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return [], True
    if not isinstance(data, list):
        return [], True
    if not all(isinstance(x, str) and CODE_RE.fullmatch(x) for x in data):
        return [], True
    if len(set(data)) != len(data):
        return [], True
    return data, False


def save(path, codes):
    """Atomic write via a temporary file so a crash never leaves a half-written file."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(codes, f, ensure_ascii=False)
    os.replace(tmp, path)


def add(path, raw):
    """Add one ticker and return a status code; never writes over a broken file."""
    with LOCK:
        codes, broken = load(path)
        if broken:
            return 'broken'
        code, err = normalize(raw)
        if err:
            return err
        if code in codes:
            return 'exists'
        if len(codes) >= MAX:
            return 'full'
        codes.append(code)
        save(path, codes)
        return 'added'


def remove(path, raw):
    """Remove one ticker; returns 'absent' silently if it was not in the list."""
    with LOCK:
        codes, broken = load(path)
        if broken:
            return 'broken'
        code, err = normalize(raw)
        if err:
            return err
        if code not in codes:
            return 'absent'
        codes.remove(code)
        save(path, codes)
        return 'removed'
