'''Reliability page of the panel (/guvenilirlik): the measured results as three small charts.

Numbers are fixed results from docs/results.md and PROJECT_NOTES.md (each decided by a rule written
before its run); nothing is read from data/. The 95% upper bounds are computed here (one-sided
Clopper-Pearson), not typed in. Inline SVG, no JavaScript (strict CSP), native <title> tooltips,
a table view under every chart, colours from the theme: accent = the live system, grey = a baseline
or an earlier stage; every bar is also labelled, so colour is never the only cue.

Usage:
  python scripts/reliability.py --self-test
'''
import argparse
import html
from math import comb

e=lambda x:html.escape('' if x is None else str(x))

# (label, silent errors, n, live?) -- docs/results.md "Extraction"
EXTRACTION=[('Set A · geliştirme seti',0,100,False),('Set B · dondurulmuş sistem, yeni set',4,100,False),
            ('Set C · + kod kontrolleri, yeni set',1,100,True)]
# without an LLM, same Set C and gold -- regex_baseline_rule.md result (11 Nov)
NO_LLM=[('En iyi regex',25,100,False),('Regex + tüm kod kontrolleri',23,100,False),('Canlı sistem (LLM + kod kontrolleri)',1,100,True)]
# amount attack: silent successes without and with each defence, on its own new texts (9 Nov)
ASSISTANT=[('Göreli dönemler ("geçen hafta", "son 3 ay"), 15 yeni soru','tarih tam doğru 10/10; yanlış dönem 1/5; eski 205 soruda yanlış 0/9','benimsendi'),
           ('Masalara e-posta (n8n, yerel posta), 15 gün, 43 bildirim','kayıp 0, çift 0, yanlış masa 0, tutar sızıntısı 0; günde 0,2 sn','benimsendi'),
           ('Kapsam dışı soru filtresi v2 (router), 20 yeni soru','kapsam dışı 10/10 engellendi, ama normal soruların 29/185\'i de','reddedildi')]
ATTACK=[('Metin kalıbı kontrolü',10,10,20,'reddedildi'),('Matriks karşılaştırması',11,2,20,'reddedildi'),
        ('Katmanlı savunma',9,0,18,'benimsendi')]
TILES=[('1/100','sessiz hata','yeni 100 bildirimde (Set C); %95 üst sınır {ub}'),
       ('11/100','insana gönderildi','şüpheli çıkarım "kontrol et" ile işaretlendi'),
       ('0/18','sessiz saldırı','gizli talimat cümlesi, katmanlı savunma ile'),
       ('11/12','günün en önemlisi','proje sahibinin kör seçimiyle aynı (sıralama v2)')]
W,LABEL,ROW,BAR=640,230,30,14


def upper95(k,n):
    '''One-sided 95% Clopper-Pearson upper bound for k events in n trials.'''
    if k>=n:
        return 1.0
    cdf=lambda p:sum(comb(n,i)*p**i*(1-p)**(n-i) for i in range(k+1))
    lo,hi=k/n,1.0
    for _ in range(60):
        mid=(lo+hi)/2
        lo,hi=(mid,hi) if cdf(mid)>0.05 else (lo,mid)
    return hi


def pct(x,digits=1):
    return f'%{x*100:.{digits}f}'.replace('.',',')


def x_of(v,vmax):
    return LABEL+v/vmax*(W-LABEL-90)


def bars(rows,vmax,unit):
    '''Horizontal bars: rows of (label, value, upper or None, live, value text, tooltip).'''
    h=ROW*len(rows)+40
    out=[f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{e(unit)}">']
    for t in range(0,int(vmax)+1,5):
        x=x_of(t,vmax)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="4" y2="{h-34}" style="stroke:var(--line);stroke-width:1"/>'
                   f'<text x="{x:.1f}" y="{h-20}" text-anchor="middle" style="fill:var(--muted);font-size:11px">{t}</text>')
    out.append(f'<text x="{x_of(vmax/2,vmax):.1f}" y="{h-3}" text-anchor="middle" style="fill:var(--muted);font-size:11px">'
               '100 bildirimde sessiz hata</text>')
    for i,(label,v,ub,live,vt,tip) in enumerate(rows):
        y=8+i*ROW
        colour='var(--accent)' if live else 'var(--muted)'
        w=max(x_of(v,vmax)-LABEL,2)
        out.append(f'<g><title>{e(tip)}</title>'
                   f'<text x="{LABEL-8}" y="{y+BAR-2}" text-anchor="end" style="fill:var(--ink);font-size:12px'
                   f'{";font-weight:600" if live else ""}">{e(label)}</text>'
                   f'<rect x="{LABEL}" y="{y}" width="{w:.1f}" height="{BAR}" rx="3" style="fill:{colour}"/>')
        end=x_of(v,vmax)
        if ub is not None:
            xu=x_of(ub,vmax)
            out.append(f'<line x1="{end:.1f}" x2="{xu:.1f}" y1="{y+BAR/2}" y2="{y+BAR/2}" style="stroke:var(--ink);stroke-width:1.5"/>'
                       f'<line x1="{xu:.1f}" x2="{xu:.1f}" y1="{y+2}" y2="{y+BAR-2}" style="stroke:var(--ink);stroke-width:1.5"/>')
            end=xu
        out.append(f'<text x="{end+6:.1f}" y="{y+BAR-2}" style="fill:var(--ink);font-size:12px;paint-order:stroke;stroke:var(--bg);stroke-width:4px;stroke-linejoin:round">{e(vt)}</text></g>')
    out.append('</svg>')
    return ''.join(out)


def paired(rows):
    '''Two bars per defence (without / with), as % of its texts; rows of (label, before, after, n, decision).'''
    h=ROW*2*len(rows)+24
    out=[f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="Sessiz saldırı başarısı, savunmasız ve savunmalı">']
    for t in range(0,101,20):
        x=x_of(t,100)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="4" y2="{h-18}" style="stroke:var(--line);stroke-width:1"/>'
                   f'<text x="{x:.1f}" y="{h-4}" text-anchor="middle" style="fill:var(--muted);font-size:11px">%{t}</text>')
    for i,(label,b,a,n,dec) in enumerate(rows):
        y=8+i*2*ROW
        out.append(f'<text x="{LABEL-8}" y="{y+BAR+4}" text-anchor="end" style="fill:var(--ink);font-size:12px">{e(label)}</text>'
                   f'<text x="{LABEL-8}" y="{y+BAR+18}" text-anchor="end" style="fill:var(--muted);font-size:11px">{e(dec)}</text>')
        for j,(v,colour,word) in enumerate(((b,'var(--muted)','savunmasız'),(a,'var(--accent)','savunmalı'))):
            yy=y+j*(BAR+2)
            w=max(x_of(v/n*100,100)-LABEL,2)
            out.append(f'<g><title>{e(label)}, {word}: {v}/{n} sessiz başarı</title>'
                       f'<rect x="{LABEL}" y="{yy}" width="{w:.1f}" height="{BAR}" rx="3" style="fill:{colour}"/>'
                       f'<text x="{LABEL+w+6:.1f}" y="{yy+BAR-2}" style="fill:var(--ink);font-size:12px;paint-order:stroke;stroke:var(--bg);stroke-width:4px;stroke-linejoin:round">{v}/{n} {word}</text></g>')
    out.append('</svg>')
    return ''.join(out)


def table(head,rows):
    th=''.join(f'<th>{e(h)}</th>' for h in head)
    tr=''.join('<tr>'+''.join(f'<td>{e(c)}</td>' for c in r)+'</tr>' for r in rows)
    return f'<details class="muted"><summary>Tablo</summary><table class="t"><tr>{th}</tr>{tr}</table></details>'


def render_body(nav):
    ub_c=upper95(1,100)
    tiles=''.join(f'<div class="tile"><b>{e(v)}</b><span>{e(k)}</span><small>{e(d.format(ub=pct(ub_c)))}</small></div>'
                  for v,k,d in TILES)
    ext=[(l,k,upper95(k,n)*100,live,f'{k}/{n} (üst sınır {pct(upper95(k,n))})',
          f'{l}: {k}/{n} sessiz hata, %95 üst sınır {pct(upper95(k,n))}') for l,k,n,live in EXTRACTION]
    nollm=[(l,k,None,live,f'{k}/{n}',f'{l}: {k}/{n} sessiz hata') for l,k,n,live in NO_LLM]
    parts=[nav,'<h1>Ölçülmüş güvenilirlik</h1>',
           '<p class="muted">Her sonuç, ölçümden önce yazılmış bir karar kuralıyla tek seferde alındı. '
           'Sessiz hata: tutar veya para birimi yanlış ve sistem uyarı vermedi.</p>',
           f'<div class="tiles">{tiles}</div>',
           '<h2>1. Tutar çıkarımı: sessiz hata (100 bildirimde)</h2>',
           '<p class="muted">Geliştirme setinde 0 hata yeni sette tutmadı (Set B, kural: başarısız). Hatalar incelendi, '
           'kod kontrolleri eklendi, hiç görülmemiş Set C ile yeniden ölçüldü. Çizgi: %95 üst sınır.</p>',
           f'<figure class="rel">{bars(ext,25,"Sessiz hata, 100 bildirimde")}</figure>',
           table(('set','sessiz hata','%95 üst sınır'),[(l,f'{k}/{n}',pct(upper95(k,n))) for l,k,n,_ in EXTRACTION]),
           '<h2>2. LLM olmadan çözülebilir miydi?</h2>',
           '<p class="muted">Aynı 100 bildirim, aynı doğru cevaplar. En iyi kural tabanlı sistem işlerin yaklaşık dörtte birini '
           'uyarısız yanlış okuyor; çoğu, kalıbın kapsamadığı yazımlar ve birden fazla tutar.</p>',
           f'<figure class="rel">{bars(nollm,30,"Sessiz hata, LLM olmadan ve LLM ile")}</figure>',
           table(('sistem','sessiz hata'),[(l,f'{k}/{n}') for l,k,n,_ in NO_LLM]),
           '<h2>3. Bildirim metnine gizlenen talimat (kırmızı takım)</h2>',
           '<p class="muted">Metne eklenen tek bir cümle tutarı değiştirmeye çalışıyor. Her savunma kendi yeni metinlerinde ve '
           'görmediğimiz saldırı cümleleriyle ölçüldü; iki savunma kuralı geçemedi, katmanlı savunma benimsendi.</p>',
           f'<figure class="rel">{paired(ATTACK)}</figure>',
           table(('savunma','savunmasız','savunmalı','karar'),[(l,f'{b}/{n}',f'{a}/{n}',d) for l,b,a,n,d in ATTACK]),
           '<h2>4. Asistan ve masalara teslimat</h2>',
           '<p class="muted">Aynı yöntem: kural önce, yeni sorular, tek ölçüm. Reddedilenler de burada.</p>',
           '<table class="t"><tr>'+''.join(f'<th>{e(h)}</th>' for h in ('ne','sonuç','karar'))+'</tr>'+
           ''.join('<tr>'+''.join(f'<td>{e(c)}</td>' for c in r)+'</tr>' for r in ASSISTANT)+'</table>',
           '<p class="muted">Sınırlar: test setleri küçük (100 / 20 / 18), bu yüzden üst sınırlar geniş; tek analist etiketledi. '
           'Ayrıntılar: docs/results.md.</p>']
    return ''.join(parts)


CSS='''.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;margin:14px 0 6px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:2px}
.tile b{font-size:1.6rem;color:var(--ink)}.tile span{font-weight:600}.tile small{color:var(--muted)}
.rel{margin:6px 0}.rel svg{width:100%;max-width:960px;height:auto;display:block}
table.t{border-collapse:collapse;margin:6px 0}table.t td,table.t th{border-bottom:1px solid var(--line);padding:3px 10px;text-align:left}'''


def _self_test():
    assert abs(upper95(1,100)-0.0466)<0.0005 and abs(upper95(0,100)-0.0295)<0.0005   # notes: 4.7% and 3.0%
    assert abs(upper95(0,18)-0.153)<0.001 and upper95(5,5)==1.0                     # notes: 0/18 -> 15.3%
    s=bars([('A',4,8.8,False,'4/100','t'),('<b>',1,4.7,True,'1/100','t')],25,'u')
    assert '100 bildirimde sessiz hata' in s and '>15</text>' in s and s.count('<rect')==2 and 'var(--accent)' in s and '&lt;b&gt;' in s and '<b>' not in s and '<script' not in s
    p=paired(ATTACK)
    assert p.count('<rect')==6 and '0/18 savunmalı' in p and '%100' in p
    body=render_body('<nav></nav>')
    assert body.count('<figure class="rel">')==3 and body.count('<summary>Tablo</summary>')==3 and '%4,7' in body
    assert body.count('<td>reddedildi</td>')==3 and '29/185&#x27;i' in body and '<h2>4.' in body   # 2 attack rows + scope v2
    print('self-test ok: 6 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    else:
        ap.error('give --self-test (the page is served by panel.py at /guvenilirlik)')


if __name__=='__main__':
    main()
