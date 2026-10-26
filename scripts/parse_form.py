import glob
import json

from bs4 import BeautifulSoup


def parse_form(content):
    soup=BeautifulSoup(content or '','html.parser')
    form={}
    for row in soup.find_all('tr'):
        tds=row.find_all('td')
        if len(tds)!=2:
            continue
        key=tds[0].get_text(' ',strip=True)
        value=tds[1].get_text(' ',strip=True)
        form[key]=value
    return form


if __name__=='__main__':
    path=sorted(glob.glob('data/kap_probe_*.json'))[-1]
    items=json.load(open(path,encoding='utf-8'))
    for item in items:
        form=parse_form(item['content'])
        print(item['headline'][:60])
        print('  ',form.get('Açıklama','')[:100])