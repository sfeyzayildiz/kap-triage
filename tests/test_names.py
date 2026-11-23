'''kap_triage/assistant/names.py: the checks of the v1 self-test in names.py, on made-up data (no network, no real data).'''
from kap_triage.assistant.names import _DISPLAY, company_label, fold, mentions, parse_names


def test_names():
    table='# c\nFONET: Fonet; Fonet Bilgi Teknolojileri\nASELS: Aselsan\nASTOR: Astor Enerji\nTUPRS: \nX: ab\n'
    names,filled=parse_names(table)
    assert filled==4 and ('ab',) not in [w for w,_ in names]                       # too short a name is dropped
    syms={'FONET','ASELS','ASTOR','TUPRS','KONTR'}
    assert mentions('Fonet Bilgi Teknolojileri\'nin Aydın sözleşmesi',syms,names)==['FONET']
    assert mentions('Aselsan\'ın Irak işi',syms,names)==['ASELS']                    # suffix after apostrophe
    assert mentions('Aselsanın son işleri',syms,names)==['ASELS']                    # suffix glued on
    assert mentions('ASELSAN İŞLERİ',syms,names)==['ASELS']                           # capitals fold
    assert mentions('Aselsan ASTOR ile anlaştı mı',syms,names)==['ASELS','ASTOR']    # order of appearance
    assert mentions('ASTOR ile Aselsan',syms,names)==['ASTOR','ASELS']
    assert mentions('astor enerjinin sözleşmesi',syms,names)==['ASTOR']
    assert mentions('KONTR neden yükseldi',syms,names)==['KONTR']                   # ticker without a name row
    assert mentions('kontr neden yükseldi',syms,names)==[]                          # lower-case ticker is not a ticker
    assert mentions('enerji sözleşmeleri',syms,names)==[]                           # a later word alone does not match
    assert mentions('Fonetik bir soru',syms,[(('fon',),'FONET')])==[]               # short name: no suffix match
    assert fold('İSTANBUL')=='istanbul' and fold('IĞDIR')=='igdir'
    saved=dict(_DISPLAY)
    _DISPLAY.clear()
    _DISPLAY.update({'ASELS':'Aselsan'})
    assert company_label('ASELS')=='Aselsan (ASELS)' and company_label('ASELS',short=True)=='Aselsan'
    assert company_label('ZZZZ')=='ZZZZ' and company_label(None) is None
    _DISPLAY.clear()
    _DISPLAY.update(saved)


def test_check_counts(tmp_path,capsys):
    # the --check summary on a made-up name table: 3 symbols, 2 with a name, the comment line skipped
    from kap_triage.assistant.names import check
    p=tmp_path/'company_names.txt'
    p.write_text('# comment: x\nSVN1: Savunmatik\nENR1: Enerjix; Enerjix Grup\nBLS2:\n',encoding='utf-8')
    check(str(p))
    assert capsys.readouterr().out.startswith('symbols=3 with_name=2 ')
