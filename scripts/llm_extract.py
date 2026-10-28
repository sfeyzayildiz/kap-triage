import json
import argparse

import os
import re
import time
from pathlib import Path
from typing import Literal, Optional

import ollama
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()
MODEL=os.environ.get('OLLAMA_MODEL','gemma4:e4b')
LLM_TIMEOUT=float(os.environ.get('LLM_TIMEOUT','120'))
# fail fast if Ollama hangs; the caller records the error and moves on
# thinking: unset keeps the Ollama default (on for gemma4); 'true'/'false' forces it
THINK_ENV=os.environ.get('OLLAMA_THINK','').strip().lower()
if THINK_ENV not in ('','true','false'):
    raise ValueError(f'OLLAMA_THINK must be true, false or unset, got {THINK_ENV!r}')
THINK={'true':True,'false':False}.get(THINK_ENV)
# max generated tokens, thinking included; -1 means no limit (Ollama default)
NUM_PREDICT=int(os.environ.get('NUM_PREDICT','-1'))
CLIENT=ollama.Client(timeout=LLM_TIMEOUT)

SAMPLES_PATH=Path('data/manual_samples.txt')
OUT_PATH=Path('data/llm_preds.jsonl')


class Disclosure(BaseModel):
    # v1/v2 schema: frozen so earlier eval results stay reproducible
    company: Optional[str]
    event_type: Literal['order','contract','tender','other']
    amount: Optional[float]
    currency: Optional[Literal['USD','EUR','TRY']]
    amount_try: Optional[float]
    counterparty_name: Optional[str]
    counterparty_origin: Literal['domestic','foreign','unknown']
    related_party: Optional[bool]
    duration: Optional[str]
    subject: Optional[str]


# reasons the model may give; code-side checks add more in postprocess_v3
ReviewReason=Literal['mixed_currency','currency_unclear','multi_currency_items','share_unclear','amount_unclear','unknown_currency_code','revision_without_previous','total_lt_amount','try_stated_but_currency_try']


class DisclosureV3(BaseModel):
    # Field order matters: the model generates fields in this order, so the
    # context (revision, items, VAT, total vs. share) is decided before amount.
    company: Optional[str]
    event_type: Literal['order','contract','tender','other']
    counterparty_name: Optional[str]
    counterparty_origin: Literal['domestic','foreign','unknown']
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


# each prompt version is tied to the schema it was evaluated with
SCHEMAS={'v1':Disclosure,'v2':Disclosure,'v3':DisclosureV3}

PROMPT_DIR=Path(__file__).resolve().parent.parent/'prompts'
DEFAULT_PROMPT='v2'


def load_prompt(version=DEFAULT_PROMPT):
    return (PROMPT_DIR/f'extract_{version}.txt').read_text(encoding='utf-8')


PROMPT=load_prompt()


def load_samples(path):
    text=path.read_text(encoding='utf-8')
    samples={}
    for block in text.split('### ')[1:]:
        header,_,body=block.partition('\n')
        m=re.match(r'(\d+)',header.strip())
        if m:
            samples[int(m.group(1))]=body.strip()
    return samples

CUR_WORDS={
    '₺':'TRY','tl':'TRY','türk lirası':'TRY',
    '?':'TRY',  # ₺ lost in encoding upstream (shows up as a literal '?')
    '$':'USD','usd':'USD','abd doları':'USD',
    '€':'EUR','eur':'EUR','avro':'EUR','euro':'EUR',
}

# currencies we accept without review; anything else is flagged
ISO_CURRENCIES={
    'TRY','USD','EUR','GBP','CHF','JPY','CNY','RUB','CAD','AUD',
    'SEK','NOK','DKK','PLN','RON','SAR','AED','QAR','KWD','IQD',
    'EGP','AZN','KZT','UZS','GEL',
}
CUR_ALIASES={
    'TL':'TRY','YTL':'TRY','₺':'TRY','$':'USD','€':'EUR','£':'GBP',
    'DOLAR':'USD','EURO':'EUR','AVRO':'EUR',
}


def tr_number(x):
    # 155413239.52 -> '155.413.239,52' (also '750.000.000' for whole numbers)
    s=f'{x:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    return [s,s[:-3]] if s.endswith(',00') else [s]


def currency_from_text(amount,text):
    low=text.lower()
    for num in tr_number(amount):
        i=low.find(num)
        if i==-1:
            continue
        after=low[i+len(num):i+len(num)+15]
        # pick the currency mentioned closest to the number
        hits=[(after.find(k),v) for k,v in CUR_WORDS.items() if k in after]
        if hits:
            return min(hits)[1]
    return None


def normalize_currency(c):
    # returns (code, known); None counts as known (nothing to review)
    if not c:
        return None,True
    s=c.strip().upper()
    s=CUR_ALIASES.get(s,s)
    return s,s in ISO_CURRENCIES

FOREIGN_CODES=[c for c in ISO_CURRENCIES if c!='TRY']
FOREIGN_WORDS=['DOLAR','DOLARI','AVRO','EURO']
FOREIGN_SYMBOLS=['$','€','£']


def mentions_foreign_currency(text):
    up=(text or '').upper()
    # word boundaries: 'GEL' (Georgian lari) must not match inside 'GELIR'
    for w in FOREIGN_CODES+FOREIGN_WORDS:
        if re.search(rf'\b{w}\b',up):
            return True
    return any(s in up for s in FOREIGN_SYMBOLS)



def postprocess_v3(data,text):
    reasons=list(data.get('needs_review_reasons') or [])
    if data.get('amount') is not None and not data.get('currency'):
        data['currency']=currency_from_text(data['amount'],text)
    cur,known=normalize_currency(data.get('currency'))
    data['currency']=cur
    if not known:
        reasons.append('unknown_currency_code')
    if data.get('is_revision') and data.get('previous_amount') is None:
        reasons.append('revision_without_previous')
    total,amount=data.get('total_amount'),data.get('amount')
    if total is not None and amount is not None and total<amount:
        reasons.append('total_lt_amount')
    # a TL equivalent only makes sense when the contract currency is not TL
    if cur=='TRY' and data.get('amount_try_stated') is not None:
        if mentions_foreign_currency(text):
            # TL chosen although another currency is in the text: maybe a conversion was picked
            reasons.append('try_stated_but_currency_try')
        else:
            data['amount_try_stated']=None
    data['needs_review_reasons']=list(dict.fromkeys(reasons))
    data['needs_review']=bool(data['needs_review_reasons'])
    return data


def call_llm(text,retries=1,prompt=None,version=None):
    version=version or DEFAULT_PROMPT
    if version not in SCHEMAS:
        raise ValueError(f'no schema for prompt version {version!r}; add it to SCHEMAS')
    schema=SCHEMAS[version]
    messages=[{'role':'user','content':(prompt or load_prompt(version))+text}]
    for attempt in range(retries+1):
        extra={} if THINK is None else {'think':THINK}
        resp=CLIENT.chat(
            model=MODEL,
            messages=messages,
            format=schema.model_json_schema(),
            options={'temperature':0,'num_ctx':8192,'num_predict':NUM_PREDICT},
            **extra,
        )
        content=resp.message.content
        try:
            data=schema.model_validate_json(content).model_dump()
            if schema is DisclosureV3:
                return postprocess_v3(data,text)
            # v1/v2: model found the amount but not the currency
            if data.get('amount') is not None and data.get('currency') is None:
                data['currency']=currency_from_text(data['amount'],text)
            return data
        except ValidationError as e:
            print(f'  invalid output (attempt {attempt+1}): {str(e)[:300]}')
            # show the model its own output and the error, then ask again
            messages=messages+[
                {'role':'assistant','content':content},
                {'role':'user','content':f'Your output was invalid: {str(e)[:500]}\nReturn the corrected JSON only.'},
            ]
    return None


def main():
    parser=argparse.ArgumentParser(description='Run LLM extraction on the dev set.')
    parser.add_argument('--prompt',default=DEFAULT_PROMPT,help='prompt version, e.g. v2 or v3')
    args=parser.parse_args()

    version=args.prompt
    prompt=load_prompt(version)
    # the default prompt keeps the original file, so earlier results stay reproducible
    if version==DEFAULT_PROMPT:
        out_path=OUT_PATH
    else:
        out_path=OUT_PATH.with_name(f'{OUT_PATH.stem}_{version}.jsonl')

    samples=load_samples(SAMPLES_PATH)
    print(f'{len(samples)} samples loaded, model: {MODEL}, prompt: {version}')
    start=time.time()
    with out_path.open('w',encoding='utf-8') as f:
        for sid,text in sorted(samples.items()):
            t0=time.time()
            pred=call_llm(text,prompt=prompt,version=version) or {}
            pred['id']=sid
            pred['prompt_version']=version
            f.write(json.dumps(pred,ensure_ascii=False)+'\n')
            print(f'id {sid}: {time.time()-t0:.1f}s')
    print(f'Saved to {out_path} | total {time.time()-start:.0f}s')


if __name__=='__main__':
    main()