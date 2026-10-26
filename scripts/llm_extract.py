'''LLM-based structured extraction for KAP disclosures (local model via Ollama).

Reads data/manual_samples.txt, sends each sample to a local Ollama model with a fixed
JSON schema, writes predictions to data/llm_preds.jsonl (gitignored, never committed).
Nothing leaves this machine.
'''
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


PROMPT='''You extract structured data from Turkish KAP (Public Disclosure Platform) announcements
about new orders, contracts and tenders. Fill the JSON schema using these rules:

- company: issuing company name as written in the header, short form is fine
- event_type: "order", "contract", "tender" or "other"
- amount: the main deal amount in its ORIGINAL currency, as a plain number.
  Convert words: "15 milyon" -> 15000000, "1,2 milyar" -> 1200000000.
  If several amounts appear, pick the main order/contract value, not approximations or other figures.
- currency: "USD", "EUR", "TRY" or null
- amount_try: Turkish lira equivalent ONLY if the text explicitly states it, else null
- counterparty_name: counterparty as written (may be partial), else null
- counterparty_origin: "domestic" or "foreign" ONLY if the text explicitly says so
  (e.g. "yurt ici", "yurt disi", a named foreign country); otherwise "unknown".
  Never infer origin from a company name.
- related_party: true/false ONLY if the text explicitly says so, else null
- duration: contract duration or delivery deadline as a short string, else null
- subject: short description of the deal, in Turkish
- counterparty_name: proper names only (full or partial, e.g. "Turkcell Grup şirketleri"). Descriptions like "bir banka" -> null.

Do not guess. Anything not explicitly stated in the text is null (or "unknown" for counterparty_origin).

Announcement:
'''


def load_samples(path):
    text=path.read_text(encoding='utf-8')
    samples={}
    for block in text.split('### ')[1:]:
        header,_,body=block.partition('\n')
        m=re.match(r'(\d+)',header.strip())
        if m:
            samples[int(m.group(1))]=body.strip()
    return samples


def call_llm(text):
    resp=ollama.chat(
        model=MODEL,
        messages=[{'role':'user','content':PROMPT+text}],
        format=Disclosure.model_json_schema(),
        options={'temperature':0},
    )
    try:
        return Disclosure.model_validate_json(resp.message.content).model_dump()
    except ValidationError as e:
        print(f'  invalid output: {str(e)[:150]}')
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