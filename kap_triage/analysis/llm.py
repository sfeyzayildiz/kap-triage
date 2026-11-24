"""Extraction with the local LLM: prompt v3, a pydantic schema, then code checks on the answer.

The model fills the fields; postprocess() only normalises the currency and adds review reasons.
It never changes an amount. Prompt, schema and settings are the ones measured on Sets A-D (frozen).
"""

import os
import re
from pathlib import Path
from typing import Literal, Optional

import ollama
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()
MODEL = os.environ.get('OLLAMA_MODEL', 'gemma4:e4b')
LLM_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', '120'))  # fail fast if Ollama hangs; the caller records the error
# thinking: unset keeps the Ollama default (on for gemma4); 'true'/'false' forces it
THINK_ENV = os.environ.get('OLLAMA_THINK', '').strip().lower()
if THINK_ENV not in ('', 'true', 'false'):
    raise ValueError(f'OLLAMA_THINK must be true, false or unset, got {THINK_ENV!r}')
THINK = {'true': True, 'false': False}.get(THINK_ENV)
NUM_PREDICT = int(os.environ.get('NUM_PREDICT', '-1'))  # max generated tokens, thinking included; -1 = no limit
CLIENT = ollama.Client(timeout=LLM_TIMEOUT)

PROMPT_VERSION = 'v3'
PROMPT = Path(__file__).with_name('prompt_v3.txt').read_text(encoding='utf-8')

# reasons the model may give; postprocess() adds more
ReviewReason = Literal[
    'mixed_currency',
    'currency_unclear',
    'multi_currency_items',
    'share_unclear',
    'amount_unclear',
    'unknown_currency_code',
    'revision_without_previous',
    'total_lt_amount',
    'try_stated_but_currency_try',
]


class DisclosureV3(BaseModel):
    # Field order matters: the model generates fields in this order, so the
    # context (revision, items, VAT, total vs. share) is decided before amount.
    # The class name is part of the JSON schema sent to Ollama; keep it as measured.
    company: Optional[str]
    event_type: Literal['order', 'contract', 'tender', 'other']
    counterparty_name: Optional[str]
    counterparty_origin: Literal['domestic', 'foreign', 'unknown']
    related_party: Optional[bool]
    is_revision: bool
    previous_amount: Optional[float]
    n_items: Optional[int]
    vat_included: bool
    total_amount: Optional[float]
    amount: Optional[float]
    currency: Optional[str]
    amount_try_stated: Optional[float]
    needs_review_reasons: list[ReviewReason]
    duration: Optional[str]
    subject: Optional[str]


CUR_WORDS = {
    '₺': 'TRY',
    'tl': 'TRY',
    'türk lirası': 'TRY',
    '?': 'TRY',  # ₺ lost in encoding upstream (shows up as a literal '?')
    '$': 'USD',
    'usd': 'USD',
    'abd doları': 'USD',
    '€': 'EUR',
    'eur': 'EUR',
    'avro': 'EUR',
    'euro': 'EUR',
}
# currencies accepted without review; anything else is flagged
ISO_CURRENCIES = {
    'TRY',
    'USD',
    'EUR',
    'GBP',
    'CHF',
    'JPY',
    'DZD',
    'CNY',
    'RUB',
    'CAD',
    'AUD',
    'SEK',
    'NOK',
    'DKK',
    'PLN',
    'RON',
    'SAR',
    'AED',
    'QAR',
    'KWD',
    'IQD',
    'EGP',
    'AZN',
    'KZT',
    'UZS',
    'GEL',
}
CUR_ALIASES = {
    'TL': 'TRY',
    'YTL': 'TRY',
    '₺': 'TRY',
    '$': 'USD',
    '€': 'EUR',
    '£': 'GBP',
    'DOLAR': 'USD',
    'EURO': 'EUR',
    'AVRO': 'EUR',
}
FOREIGN_CODES = [c for c in ISO_CURRENCIES if c != 'TRY']
FOREIGN_WORDS = ['DOLAR', 'DOLARI', 'AVRO', 'EURO']
FOREIGN_SYMBOLS = ['$', '€', '£']


def tr_number(x):
    """155413239.52 -> ['155.413.239,52']; whole numbers also without ',00'."""
    s = f'{x:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return [s, s[:-3]] if s.endswith(',00') else [s]


def currency_from_text(amount, text):
    """The currency word written closest after the amount, or None."""
    low = text.lower()
    for num in tr_number(amount):
        i = low.find(num)
        if i == -1:
            continue
        after = low[i + len(num) : i + len(num) + 15]
        hits = [(after.find(k), v) for k, v in CUR_WORDS.items() if k in after]
        if hits:
            return min(hits)[1]
    return None


def normalize_currency(c):
    """(code, known); None counts as known (nothing to review)."""
    if not c:
        return None, True
    s = c.strip().upper()
    s = CUR_ALIASES.get(s, s)
    return s, s in ISO_CURRENCIES


def mentions_foreign_currency(text):
    up = (text or '').upper()
    # word boundaries: 'GEL' (Georgian lari) must not match inside 'GELIR'
    for w in FOREIGN_CODES + FOREIGN_WORDS:
        if re.search(rf'\b{w}\b', up):
            return True
    return any(s in up for s in FOREIGN_SYMBOLS)


def postprocess(data, text):
    """Code checks on the model's answer: currency from the text if missing, review reasons. Amounts unchanged."""
    reasons = list(data.get('needs_review_reasons') or [])
    if data.get('amount') is not None and not data.get('currency'):
        data['currency'] = currency_from_text(data['amount'], text)
    cur, known = normalize_currency(data.get('currency'))
    data['currency'] = cur
    if not known:
        reasons.append('unknown_currency_code')
    if data.get('is_revision') and data.get('previous_amount') is None:
        reasons.append('revision_without_previous')
    total, amount = data.get('total_amount'), data.get('amount')
    if total is not None and amount is not None and total < amount:
        reasons.append('total_lt_amount')
    # a TL equivalent only makes sense when the contract currency is not TL
    if cur == 'TRY' and data.get('amount_try_stated') is not None:
        if mentions_foreign_currency(text):
            reasons.append('try_stated_but_currency_try')  # TL chosen although another currency is in the text
        else:
            data['amount_try_stated'] = None
    data['needs_review_reasons'] = list(dict.fromkeys(reasons))
    data['needs_review'] = bool(data['needs_review_reasons'])
    return data


def call_llm(text, retries=1):
    """One extraction. An invalid answer is shown back to the model once; None if it stays invalid."""
    messages = [{'role': 'user', 'content': PROMPT + text}]
    for attempt in range(retries + 1):
        extra = {} if THINK is None else {'think': THINK}
        resp = CLIENT.chat(
            model=MODEL,
            messages=messages,
            format=DisclosureV3.model_json_schema(),
            options={'temperature': 0, 'num_ctx': 8192, 'num_predict': NUM_PREDICT},
            **extra,
        )
        content = resp.message.content
        try:
            return postprocess(DisclosureV3.model_validate_json(content).model_dump(), text)
        except ValidationError as e:
            print(f'  invalid output (attempt {attempt + 1}): {str(e)[:300]}')
            messages = messages + [
                {'role': 'assistant', 'content': content},
                {
                    'role': 'user',
                    'content': f'Your output was invalid: {str(e)[:500]}\nReturn the corrected JSON only.',
                },
            ]
    return None
