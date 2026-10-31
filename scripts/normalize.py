'''Text normalization for RAG (embedding input only).

Rules come from the profile in text_artifacts.py (2026-10-30). The frozen
v3 extraction pipeline keeps reading the raw aciklama.
'''
import re

TR='çğıöşüÇĞİÖŞÜ'
SPLIT_HIT=re.compile(rf'(?<=\w) [{TR}] (?=\w)')
# rows with >=6 hits had every Turkish letter split off; 1-hit rows were 'İ STANBUL'
HEAVY_MIN_HITS=5
SPLIT_SPACE=re.compile(rf'(?<=[^\W\d_]) (?=[{TR}])|(?<=[{TR}]) (?=[^\W\d_])')
UPPER_SPLIT=re.compile(r'\b([İŞÇĞÜÖ]) (?=[A-ZÇĞİÖŞÜ]{2,})')
LIRA_AFTER=re.compile(r'(\d\s*)\?')
LIRA_BEFORE=re.compile(r'\?(\s*\d)')
MULTI_SPACE=re.compile(r'[ \t]{2,}')


def is_heavy(text):
    return len(SPLIT_HIT.findall(text))>=HEAVY_MIN_HITS


def fix_split(text):
    '''Join Turkish letters that were split off with spaces (heavy rows only).'''
    return SPLIT_SPACE.sub('',text)


def normalize(text):
    if not text:
        return ''
    text=text.replace('\xa0',' ')
    text=UPPER_SPLIT.sub(r'\1',text)
    if is_heavy(text):
        text=fix_split(text)
    text=LIRA_AFTER.sub(r'\1₺',text)
    text=LIRA_BEFORE.sub(r'₺\1',text)
    text=MULTI_SPACE.sub(' ',text)
    return text.strip()


def _self_test():
    cases=[
        (fix_split('aras ı nda'),'arasında'),
        (fix_split('s ö zle ş me imzal'),'sözleşme imzal'),
        (fix_split('anm ış t ı r. Ara ç lar ı m ı z ı'),'anmıştır. Araçlarımızı'),
        (fix_split('22 ara ç 12 metre'),'22 araç 12 metre'),
        # known limitation: real word boundaries next to a Turkish letter are lost
        (fix_split('29 adet ş arj'),'29 adetşarj'),
        (normalize('numaralı İ STANBUL\xa0Bölge'),'numaralı İSTANBUL Bölge'),
        (normalize('üç adet şarj'),'üç adet şarj'),
        (normalize('1.000.000 ? tutarında'),'1.000.000 ₺ tutarında'),
        (normalize('?500 bin'),'₺500 bin'),
        (normalize('Neden? Çünkü'),'Neden? Çünkü'),
        (normalize('  a\xa0\xa0 b  '),'a b'),
        (normalize(None),''),
        (is_heavy('s ö zle ş me ara ç lar ı m ı z'),True),
        (is_heavy('numaralı İ STANBUL'),False),
    ]
    failed=[(i,got,want) for i,(got,want) in enumerate(cases) if got!=want]
    for i,got,want in failed:
        print(f'case {i}: got {got!r}, want {want!r}')
    print(f'{len(cases)-len(failed)}/{len(cases)} self-tests passed')
    return not failed


if __name__=='__main__':
    raise SystemExit(0 if _self_test() else 1)