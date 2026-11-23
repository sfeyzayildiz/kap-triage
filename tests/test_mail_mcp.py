'''Tests moved from mail_mcp.py (v1 self-test).'''
import re
from kap_triage.web.mail_mcp import BAD_CASES, SERVER_ENV, decide, norm_text, server_env, synthetic_message


def test_mail_mcp():
    env=server_env()
    assert set(env)==set(SERVER_ENV)|{'PATH'} and env['SMTP_ALLOWED_RECIPIENTS']=='@masa.local' and env['ELICITATION']=='true'
    assert 'KAP_TOKEN' not in env and env['SMTP_HOST']=='127.0.0.1'
    assert norm_text('a  \r\nb\n\n')=='a\nb'
    m=synthetic_message('t')
    assert m['to']==['savunma@masa.local'] and m['subject'].startswith('[t] ') and 'KAP: https://www.kap.org.tr' in m['body']
    from kap_triage.analysis.desks import leaks
    assert not leaks(m['subject']+m['body'])
    outside=lambda c:[x for k in ('to','cc','bcc') for x in c.get(k,[]) if not re.fullmatch(r'[^@\s]+@masa\.local',x)]
    assert len(BAD_CASES)==7 and all(outside(c) for _,c in BAD_CASES)   # every A case has an address outside the allowlist
    assert decide({'a':True},1.0)=='ADOPT_SMTP_MCP' and decide({'a':True,'b':False},1.0)=='SMTP_MCP_OFF'
    assert decide({'a':True},6.0)=='SMTP_MCP_OFF' and decide({'a':True},None)=='SMTP_MCP_OFF'


def test_smtp_server_path_is_in_the_repository():
    # the pinned smtp-mcp server lives in mcp/smtp/ at the repository root, two levels above web/
    import kap_triage.web.mail_mcp as mail_mcp
    assert (mail_mcp.ROOT/'main.py').exists() and (mail_mcp.ROOT/'mcp'/'smtp'/'package.json').exists()
    assert mail_mcp.SERVER_JS.is_relative_to(mail_mcp.ROOT/'mcp'/'smtp')
