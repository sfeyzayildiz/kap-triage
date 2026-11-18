'''Demo mode, real-data leak check (docs/demo_mode_rule.md, measurement 2). Feyza runs it; stdout is counts only.

Renders the panel pages for every saved morning list with demo mode on and counts Matriks-based text:
  day pages (with the real price charts passed in, which demo mode must drop),
  the start page (chat) and the guided form with the deterministic agent answers for the day:
  morning list, period list (the day's week), and per company of the day: last-12-months list,
  why-moved, brief (built from the saved list + the SQL history step; no LLM) and the detail card,
  the themes index and every week page, the reliability page.
No LLM, no network, read-only DB (short connections). Each page is also rendered with demo mode off
("seen_off": proves the check can see what it counts) and, for sector names, with demo mode on and an
order-preserving neutral sector table: a demo page that differs between the two depends on a sector
name (Amendment 1; a plain name count would also hit company names and KAP text, e.g. "... Enerji").

Usage:
  python scripts/demo_leak_check.py          # ~1-3 min; prints counts and LEAKS=n
'''
import argparse
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta

import demo_mode

# template phrases our code writes only from Matriks values (searched in <body>)
PHRASES={
    'revenue_ratio':re.compile(r'tutar / şirketin yıllık geliri'),
    'history_ratio':re.compile(r'şirketin önceki işlerinin medyanının'),
    'try_size':re.compile(r'TL karşılığına göre büyüklük'),
    'no_rate':re.compile(r'için kur yok, büyüklük hesaplanmadı'),
    'index_xu100':re.compile(r'XU100'),
    'reaction':re.compile(r'tepki günü'),
    'price_line':re.compile(r'Fiyat: (?!'+re.escape(demo_mode.PLACEHOLDER)+')'),
    'why_moved':re.compile(r'hisse [+-]\d'),
    'z_value':re.compile(r'\(z -?\d|eşik z \d'),
    'chart':re.compile(r'<figure class="chart"|<svg'),
    'score':re.compile(r'skor -?\d'),
    'matriks_label':re.compile(r'\(Matriks kaydı\)'),
    'matriks_count':re.compile(r'Matriks tutar kaydı'),
    'matriks_amount_field':re.compile(r'\| (?:yeni|güncelleme|güncelleme/düzeltme) \| (?!'+re.escape(demo_mode.PLACEHOLDER)+r' \|)[^|<]* \|'),
    'sector_line':re.compile(r'sektörler: '),
}
SKIP_SVG=('reliability',)  # its charts are our own measured results, not prices


def body(page):
    return page.split('<body>',1)[-1]


def counts(kind,page):
    b=body(page)
    return {k:len(rx.findall(b)) for k,rx in PHRASES.items() if not (k=='chart' and kind in SKIP_SVG)}


def neutral_table(sectors):
    '''Same symbols, sector names replaced by NOTR001... in the same sorted order (same desk numbers).'''
    rank={s:i for i,s in enumerate(sorted({v for v in sectors.values() if v}),1)}
    return {sym:(f'NOTR{rank[s]:03d}' if s else s) for sym,s in sectors.items()}


def render_both(fn):
    '''(demo on, demo off) HTML of one page.'''
    demo_mode.ON=True
    try:
        on=fn()
    finally:
        demo_mode.ON=False
    return on,fn()


def day_answers(day,items,errors):
    '''Deterministic agent answers for one saved day: (question kind, symbol or None, text).'''
    import agent
    from morning import render
    from themes import week_start
    out=[('morning',None,render(day,items))]
    ws=week_start(day)
    try:
        out.append(('period',None,agent.period_list(str(ws),str(min(ws+timedelta(days=6),date.fromisoformat(day))))))
    except Exception as ex:
        errors[f'period:{type(ex).__name__}']+=1
    for it in {i['symbol']:i for i in items if i.get('symbol')}.values():
        sym=it['symbol']
        hit={k:it.get(k) for k in ('news_id','kap_url','symbol','published_at')}
        for kind,fn in (('company',lambda:agent.tool_company({'symbol':sym,'day':day})),
                        ('why_moved',lambda:agent.tool_why_moved({'symbol':sym,'day':day})),
                        ('brief',lambda:agent.compose_brief(sym,{
                            'latest':{'hit':hit,'data':it,'importance':it.get('importance')},
                            'history':agent.step_history({'symbol':sym,'day':day},{'latest':{'hit':hit}}),
                            'reaction':it.get('reaction'),'similar':it.get('similar') or []})),
                        ('detail',lambda:'\n'.join(agent.card_lines(hit,it))+'\n')):
            try:
                out.append((kind,sym,fn()))
            except Exception as ex:
                errors[f'{kind}:{type(ex).__name__}']+=1
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        return _self_test()
    now=datetime.now()
    if now.hour==23 and 40<=now.minute<=50:
        raise SystemExit('collection window, try after 23:50')
    import chat
    import form
    import panel
    import reliability
    import themes
    from price_chart import chart_for_state, charts_for_items
    demo_mode.ON=False
    sectors=panel.load_sectors()
    neutral=neutral_table(sectors)
    reviews=panel.load_reviews()
    days=panel.available_days()
    leaks,seen,pages,errors=Counter(),Counter(),Counter(),Counter()
    dependent=Counter()
    n_symbols=0

    def check(kind,fn,fn_neutral=None):
        try:
            on,off=render_both(fn)
            if fn_neutral is not None:
                demo_mode.ON=True
                try:
                    if fn_neutral()!=on:
                        dependent[kind]+=1
                finally:
                    demo_mode.ON=False
        except Exception as ex:
            errors[f'{kind}:{type(ex).__name__}']+=1
            return
        pages[kind]+=1
        leaks.update({f'{kind}.{k}':v for k,v in counts(kind,on).items() if v})
        seen.update({k:v for k,v in counts(kind,off).items()})

    for day in days:
        items=panel.load_day(day) or []
        n_symbols+=len({i.get('symbol') for i in items})
        charts=charts_for_items(items)  # real price charts: demo mode must drop them
        sources=panel.sources_for_items(items)
        check('day',lambda:panel.render_day(day,items,sectors,panel.DESKS,reviews,charts,sources),
              lambda:panel.render_day(day,items,neutral,{neutral.get(k,k):v for k,v in panel.DESKS.items()},reviews,charts,sources))
        answers=day_answers(day,items,errors)
        hist=[{'q':k,'a':a,'at':'09:00','seconds':1.0,'intent':k if k in chat.INTENT_TR else None,'error':False}
              for k,_,a in answers]
        check('chat',lambda:panel.page('KAP asistanı',chat.render_body(hist)))
        for kind,sym,a in answers:
            if kind in ('brief','why_moved'):  # the guided form, with the real price chart demo mode must drop
                try:
                    chart=chart_for_state({'intent':kind,'symbol':sym,'day':day})
                except Exception:
                    chart=''
                last={'form':{'type':kind,'symbol':sym,'day':day,'text':''},'at':'09:00','seconds':1.0,'error':False,
                      'answer':a,'chart':chart}
                check('form',lambda:panel.page('Rehberli sorgu',form.render_body({sym},{},last,chat.NAV,
                                                                                chat.render_answer,kind=kind)))
    out=themes.load_clusters()
    if out is not None:
        check('themes',lambda:panel.render_themes_index(themes.weeks(out['assign']),themes.last_clustered(out['assign']),0))
        for w,_ in themes.weeks(out['assign']):
            view=themes.week_view(out,date.fromisoformat(w))
            urls=themes.load_meta([a['news_id'] for v in view for a in v['items']])
            check('week',lambda:panel.render_week(w,view,sectors,urls),lambda:panel.render_week(w,view,neutral,urls))
    check('reliability',lambda:panel.page('Güvenilirlik',reliability.render_body(chat.NAV)))

    n_leaks=sum(leaks.values())+sum(dependent.values())
    print(f'days={len(days)} symbol-days={n_symbols} sectors={len(set(sectors.values()))} '
          f'pages: '+' '.join(f'{k}={v}' for k,v in sorted(pages.items())))
    print('leaks with demo on (must be 0): '+(' '.join(f'{k}={v}' for k,v in sorted(leaks.items())) or 'none'))
    print('sector-dependent demo pages (must be 0): '+(' '.join(f'{k}={v}' for k,v in sorted(dependent.items())) or 'none'))
    print('seen with demo off (the check can see them): '+' '.join(f'{k}={seen[k]}' for k in PHRASES))
    print('render errors (pages not checked): '+(' '.join(f'{k}={v}' for k,v in sorted(errors.items())) or 'none'))
    verdict='pass' if n_leaks==0 and not errors and days else 'INCOMPLETE' if n_leaks==0 else 'FAIL'
    print(f'LEAKS={n_leaks} -> {verdict} (measurement 2)')
    sys.exit(0 if verdict=='pass' else 1)


def _self_test():
    t=neutral_table({'A':'Gama','B':'Alfa','C':'Alfa','D':None})
    assert t=={'A':'NOTR002','B':'NOTR001','C':'NOTR001','D':None}
    assert demo_mode.desk_map(t,{})=={'NOTR001':'Masa 1','NOTR002':'Masa 2'}   # same numbers as the real names
    ph=demo_mode.PLACEHOLDER
    c=counts('chat','<body>- 2026-10-01 | yeni | 4.242.424 USD (Matriks kaydı) | x</div>'
              f'<div>- 2026-10-01 | güncelleme | {ph} | x</div>Fiyat: {ph} Fiyat: tepki günü 2026-10-02: XU100 skor 4</body>')
    assert c['matriks_amount_field']==1 and c['matriks_label']==1 and c['price_line']==1 and c['reaction']==1
    assert c['index_xu100']==1 and c['score']==1 and c['revenue_ratio']==0
    assert 'chart' not in counts('reliability','<body><svg></svg></body>') and counts('day','<body><svg>')['chart']==1
    print('self-test ok: 7 checks')


if __name__=='__main__':
    main()
