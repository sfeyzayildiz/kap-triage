'''The sample data set (kap_triage/sample.py): built into the test data folder, then read by the
real panel, agent and theme code. Checks that the chain flags what it should and nothing else.'''
import os
from collections import Counter
from datetime import date
from types import SimpleNamespace

from kap_triage.sample import BARS_TO, CHAT_EXAMPLES, CO, COMPANIES, EXPECT_CLEAN, EXPECT_FLAG, REAL_DATA, SECTORS, URL, build


def test_sample_data(clean_data_dir):   # the folder is emptied again after this test (conftest.py)
    before=sorted(os.listdir(REAL_DATA)) if REAL_DATA.is_dir() else None
    info,specs,lists=build()   # into the test data folder (conftest.py)
    key={s['news_id']:s['key'] for s in specs}
    items={key[i['news_id']]:i for v in lists.values() for i in v}
    why=lambda k:set(items[k]['importance']['needs_review_reasons'])
    per_day=Counter(str(s['at'].date()) for s in specs)

    # made-up companies: a digit in every ticker (no real BIST ticker has one), sample URLs only
    assert all(any(ch.isdigit() for ch in c[0]) for c in COMPANIES) and len(CO)==12
    assert all(s['kap_url'].startswith(URL) for s in specs)
    # one morning list per day, every disclosure in it
    assert {d:len(v) for d,v in lists.items()}==dict(per_day)
    # two model readings per disclosure, a judge call per amount
    assert info['calls']['extract']==2*len(specs)
    assert info['calls']['judge']>=sum(s['answer']['amount'] is not None for s in specs)
    # the trap texts get their flag, the clean texts and the history texts get none
    assert all(v in why(k) for k,v in EXPECT_FLAG.items())
    assert 'amount_vs_matriks' in why('injection')
    assert not any(items[k]['importance']['needs_review'] for k in EXPECT_CLEAN)
    assert not any(i['importance']['needs_review'] for k,i in items.items() if k.startswith('h_'))
    # the big FX order is high, with its reasons and an abnormal price move
    assert items['big_fx']['importance']['level']=='high'
    assert {'size_vs_revenue','foreign_currency','long_contract'}<={r['code'] for r in items['big_fx']['importance']['reasons']}
    assert items['big_fx']['reaction']['status']=='ok' and items['big_fx']['reaction']['z0']>=3
    assert items['revision']['importance']['kind']=='revision' and items['no_amount']['amount'] is None

    import kap_triage.analysis.llm as llm
    import kap_triage.assistant.agent as agent
    import kap_triage.assistant.names as names
    import kap_triage.assistant.themes as themes
    import kap_triage.web.panel as panel
    last=max(lists)
    listed=panel.available_days()
    names._DISPLAY.clear()
    day_items=panel.load_day(last)
    page=panel.render_day(last,day_items,panel.load_sectors(),{},{},None,panel.sources_for_items(day_items))
    ctx=agent.load_context()
    moved=agent.tool_why_moved({'symbol':'SVN1','day':items['big_fx']['reaction']['t0']})
    quiet=agent.tool_why_moved({'symbol':'BLS2','day':'2026-11-18'})
    # the morning tool must use the saved list: any model call would raise
    model_calls=[]
    real_client,llm.CLIENT=llm.CLIENT,SimpleNamespace(chat=lambda **kw:model_calls.append(1) or 1/0)
    try:
        morning_text=agent.tool_morning({'day':last})
    finally:
        llm.CLIENT=real_client
    overview=panel.render_overview(panel.all_day_stats(listed,{}),day_items,{},[],{})
    clusters=themes.load_clusters()
    panel.SAMPLE=True
    try:
        banner=panel.render_index(panel.available_days())
    finally:
        panel.SAMPLE=False
    names._DISPLAY.clear()

    assert listed==sorted(lists,reverse=True)
    assert f'{per_day[last]} bildirim' in page and 'Önce bak' in page and 'Kaynak cümle' in page and 'Dermanlı' in page
    assert 'Örnek veri' in banner and 'Örnek veri' not in page          # the banner only in sample mode
    assert len(ctx['symbols'])==12 and ctx['last_bar']==BARS_TO and ctx['last_disclosure']==date(2026,11,13)
    assert 'Olağandışı mı: evet' in moved and 'bildirimi var' in moved
    assert 'Olağandışı mı: evet' in quiet and 'bildirimi yok' in quiet
    assert f'{per_day[last]} bildirim' in morning_text and not model_calls
    assert clusters['k']==len(SECTORS) and len(clusters['assign'])==len(specs)
    assert overview.count('<a class="col"')==panel.CHART_DAYS and f'href="/day/{last}"' in overview
    # chat examples ask no detail question and name two sample companies
    assert not any(agent.DETAIL_RE.search(q) for q in CHAT_EXAMPLES)
    assert all(any(n in ' '.join(CHAT_EXAMPLES) for n in (c[0],c[1])) for c in (CO['SVN1'],CO['ENR1']))
    # nothing written under the real data/ folder
    assert before==(sorted(os.listdir(REAL_DATA)) if REAL_DATA.is_dir() else None)
