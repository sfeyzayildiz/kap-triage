import json
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

SAMPLES_PATH=Path('data/manual_samples.txt')
OUT_PATH=Path('data/llm_preds.jsonl')


class Disclosure(BaseModel):
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

def call_llm(text,retries=1,prompt=None):
    messages=[{'role':'user','content':(prompt or PROMPT)+text}]
    for attempt in range(retries+1):
        resp=ollama.chat(
            model=MODEL,
            messages=messages,
            format=Disclosure.model_json_schema(),
            options={'temperature':0,'num_ctx':8192},
        )
        content=resp.message.content
        try:
            data=Disclosure.model_validate_json(content).model_dump()
            # fallback: model found the amount but not the currency
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
    samples=load_samples(SAMPLES_PATH)
    print(f'{len(samples)} samples loaded, model: {MODEL}')
    start=time.time()
    with OUT_PATH.open('w',encoding='utf-8') as f:
        for sid,text in sorted(samples.items()):
            t0=time.time()
            pred=call_llm(text) or {}
            pred['id']=sid
            f.write(json.dumps(pred,ensure_ascii=False)+'\n')
            print(f'id {sid}: {time.time()-t0:.1f}s')
    print(f'Saved to {OUT_PATH} | total {time.time()-start:.0f}s')


if __name__=='__main__':
    main()