'''One entry point for the whole system.

  python main.py panel [--sample]       analyst panel on http://127.0.0.1:8765
  python main.py sample                 (re)build the made-up sample data in sample/data/
  python main.py nightly                the nightly job (collect, extract, morning list); run by launchd at 23:43
  python main.py agent "question"       ask the assistant in the terminal
  python main.py mcp                    MCP server (tools for an MCP client)
  python main.py mail --check           is the SMTP MCP server and the local inbox ready?
  python main.py mail --send --day D    desk e-mails for one day through the SMTP MCP server
  python main.py index --build          update the search index
  python main.py kart metin.txt         a KAP card from a disclosure text (also /kart in the panel)

Every command takes the options of its module; add --help to see them.
--sample (and the sample command) points the data folder to sample/data/ before anything
else is imported, so a sample run can never read or write the real data/ folder.
'''
import importlib
import os
import sys
from pathlib import Path

COMMANDS={
    'panel':'kap_triage.web.panel',
    'sample':'kap_triage.sample',
    'nightly':'kap_triage.collect.nightly',
    'agent':'kap_triage.assistant.agent',
    'mcp':'kap_triage.web.mcp_server',
    'mail':'kap_triage.web.mail_mcp',
    'index':'kap_triage.assistant.search',
    'kart':'kap_triage.web.kart',
}
SAMPLE_DATA=Path(__file__).resolve().parent/'sample'/'data'


def main():
    if len(sys.argv)<2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    command,args=sys.argv[1],sys.argv[2:]
    if command=='sample' or '--sample' in args:
        os.environ['KAP_DATA_DIR']=str(SAMPLE_DATA)
    if command=='panel' and '--stats' not in args and '--serve' not in args:
        args=['--serve']+args   # "main.py panel" starts the server
    module=importlib.import_module(COMMANDS[command])
    sys.argv=[f'main.py {command}']+args
    module.main()


if __name__=='__main__':
    main()
