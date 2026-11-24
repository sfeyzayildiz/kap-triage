"""MCP server for the agent's tools (rule: docs/mcp_rule.md). Read-only, stdio only, local clients only.

Each MCP tool builds the same state the guided form builds and runs it through the same LangGraph
graph (intent preset, so no router call): the text is the measured tool's own output.
Tool results contain licensed Matriks data: never connect a cloud client (Claude Desktop, ChatGPT ...).

Usage:
  python -m kap_triage.web.mcp_server               # stdio server (started by a client, not by hand)
"""

import contextlib
import re
import sys
from datetime import date

INSTRUCTIONS = (
    'KAP "Yeni İş İlişkisi" disclosures, local tools. Results contain licensed Matriks data: '
    'use only with a local client; never send them to a cloud service. Read-only.'
)
TOOL_INTENT = {
    'morning_list': 'morning',
    'company_history': 'company',
    'search_disclosures': 'search',
    'why_moved': 'why_moved',
    'company_brief': 'brief',
}
DAY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def build_state(tool, args, ctx):
    """(state, None) or (None, error text). Same checks as the guided form; periods via agent.period_switch."""
    from kap_triage.assistant.agent import period_switch

    intent = TOOL_INTENT.get(tool)
    if intent is None:
        return None, f'unknown tool {tool}'
    symbol = (args.get('symbol') or '').strip().upper() or None
    if symbol and symbol not in ctx['symbols']:
        return None, f'{symbol}: bu hisse kodunun bildirimi yok.'
    if intent in ('company', 'why_moved', 'brief') and not symbol:
        return None, 'Bu araç için hisse kodu gerekli (ör. ASELS).'
    raw = (args.get('day') or '').strip()
    if raw and not DAY_RE.match(raw):
        return None, 'Tarih YYYY-AA-GG biçiminde olmalı.'
    day = date.fromisoformat(raw) if raw else None
    note = None
    if intent == 'morning' and (day is None or day > ctx['last_disclosure']):
        note = None if day is None else f'{day} henüz toplanmadı; son toplanan gün gösteriliyor.'
        day = ctx['last_disclosure']
    if intent == 'why_moved' and (day is None or day > ctx['last_bar']):
        note = f'Fiyat verisi {ctx["last_bar"]} tarihinde bitiyor; o gün kullanıldı.'
        day = ctx['last_bar']
    query = (args.get('query') or '').strip() or None
    if intent == 'search' and not query:
        return None, 'Arama için konu gerekli.'
    question = ' '.join(filter(None, [symbol, query])) or tool
    state = {
        'question': question,
        'intent': intent,
        'symbol': symbol,
        'day': str(day) if day else None,
        'query': query,
        'note': note,
        'date_filter': False,
    }
    phrase = (args.get('period') or '').strip()
    if phrase and intent == 'company':
        state = period_switch(state, phrase, ctx)
        if not state.get('period'):
            return None, f'Dönem okunamadı: "{phrase}" (ör. "geçen ay", "son 3 ay", "bu yıl").'
    return state, None


def run_tool(tool, args, ctx=None, runner=None):
    """Answer text of one tool call; never raises. stdout is kept free (it is the MCP channel)."""
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from kap_triage.assistant.agent import TOOLS, build_graph, llm_route, load_context

            ctx = ctx or load_context()
            state, err = build_state(tool, args, ctx)
            if err:
                return err
            out = (runner or (lambda st: build_graph(llm_route, TOOLS, ctx).invoke(st)))(state)
            return out.get('answer') or ''
    except Exception as e:
        return f'Araç hatası: {type(e).__name__}'


def make_server():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP('kap-triage', instructions=INSTRUCTIONS, log_level='WARNING')

    @mcp.tool()
    def morning_list(day: str = '') -> str:
        """Ranked morning list of new-business disclosures for a day (YYYY-MM-DD; empty = last collected day).
        Look-first and check-flagged items on top, each with its KAP link."""
        return run_tool('morning_list', {'day': day})

    @mcp.tool()
    def company_history(symbol: str, period: str = '') -> str:
        """A company's new-business disclosures: last 12 months, or a Turkish period phrase
        such as "geçen ay", "son 3 ay", "bu yıl". symbol = BIST ticker, e.g. ASELS."""
        return run_tool('company_history', {'symbol': symbol, 'period': period})

    @mcp.tool()
    def search_disclosures(query: str, symbol: str = '') -> str:
        """Semantic search over all disclosures (embedding top 20, cross-encoder rerank, top 5 with KAP links).
        Optional symbol restricts it to one company."""
        return run_tool('search_disclosures', {'query': query, 'symbol': symbol})

    @mcp.tool()
    def why_moved(symbol: str, day: str = '') -> str:
        """Why did a stock move on a day: return vs XU100, whether it was unusual, and new-business disclosures
        in the 4 days before (or an honest "no disclosure"). day = YYYY-MM-DD; empty = last price day."""
        return run_tool('why_moved', {'symbol': symbol, 'day': day})

    @mcp.tool()
    def company_brief(symbol: str) -> str:
        """Multi-step company brief: latest disclosure with its card and importance, price reaction,
        12-month history, similar earlier disclosures."""
        return run_tool('company_brief', {'symbol': symbol})

    return mcp


def main():
    make_server().run()  # stdio


if __name__ == '__main__':
    main()
