"""Desk e-mails for n8n (rule: docs/n8n_routing_rule.md). Code decides desk, order and text; n8n only sends.

`payload(day, items, sectors, desks)` -> {'day', 'desks': [{'desk', 'to', 'subject', 'text', 'kap_urls'}]}.
Least data: company, look-first / check flags, reason labels without numbers, KAP link, panel link.
No amounts, ratios, currencies or disclosure text (the desk opens the card in the panel).

"""

import re

DOMAIN = 'masa.local'
PANEL = 'http://127.0.0.1:8765'
# reason codes -> labels without numbers (morning.reason_text carries ratios and amounts; not for e-mail)
REASON_LABEL = {
    'size_vs_history': 'şirketin önceki işlerine göre büyük',
    'size_vs_revenue': 'şirketin gelirine göre büyük',
    'size_absolute': 'TL karşılığına göre büyük',
    'foreign_currency': 'dövizli',
    'foreign_counterparty': 'yurt dışı karşı taraf',
    'long_contract': 'uzun süreli',
    'related_party': 'ilişkili taraf (grup içi)',
    'revision': 'revizyon',
    'no_amount': 'tutar yok',
    'no_rate': 'kur yok, büyüklük hesaplanmadı',
    'no_increase': 'tutar artmamış',
}
FOLD = str.maketrans('çğıöşüâîû', 'cgiosuaiu')


def mailbox(desk):
    """ "Savunma ve Havacılık" -> savunma-ve-havacilik@masa.local (ASCII, stable)."""
    s = (desk or '').replace('İ', 'i').replace('I', 'ı').lower().replace('̇', '').translate(FOLD)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60].strip('-') or 'atanmamis'
    return f'{s}@{DOMAIN}'


def look_first(item):
    imp = item['importance']
    return bool(imp['needs_review'] or imp['level'] == 'high')


def item_lines(n, item):
    from kap_triage.analysis.morning import REVIEW_TR
    from kap_triage.assistant.names import company_label

    imp = item['importance']
    tags = []
    if imp['level'] == 'high':
        tags.append('ÖNCE BAK')
    if imp['needs_review']:
        tags.append('KONTROL ET: ' + '; '.join(REVIEW_TR.get(c, c) for c in imp['needs_review_reasons']))
    head = f'{n}. {company_label(item["symbol"])}' + (f' - {" | ".join(tags)}' if tags else '')
    lines = [head]
    reasons = [REASON_LABEL[r['code']] for r in imp.get('reasons', []) if r.get('code') in REASON_LABEL]
    if reasons:
        lines.append('   Neden: ' + ', '.join(dict.fromkeys(reasons)))
    lines.append(f'   KAP: {item.get("kap_url")}')
    return lines


def payload(day, items, sectors, desks):
    """One e-mail per desk that has items (morning priority order inside, desks as in the panel)."""
    from kap_triage.web.panel import by_desk

    out = []
    for desk, its in by_desk(items, sectors, desks).items():
        k = sum(look_first(i) for i in its)
        m = sum(bool(i['importance']['needs_review']) for i in its)
        lines = [f'Masa: {desk}', f'Gün: {day}', f'{len(its)} bildirim; önce bak {k}, kontrol et {m}.', '']
        for n, i in enumerate(its, 1):
            lines += item_lines(n, i)
        lines += [
            '',
            f'Panel (tutar, kart, kontrol): {PANEL}/day/{day}',
            'Kaynak: KAP bildirimleri ve Matriks verisi. Sıralama kurallıdır, tahmin değildir; karar öncesi KAP metnini okuyun.',
            'Bu e-posta yerel KAP asistanı tarafından oluşturuldu; masa ataması Matriks sektörüne göredir.',
        ]
        out.append(
            {
                'desk': desk,
                'to': mailbox(desk),
                'subject': f'{day} | {desk}: {len(its)} bildirim, {k} önce bak',
                'text': '\n'.join(lines) + '\n',
                'kap_urls': [i.get('kap_url') for i in its],
            }
        )
    return {'day': day, 'desks': out}


MONEY_LEAK_RE = re.compile(r'\d[\d.,]*\s*(%|tl\b|try\b|usd\b|eur\b|dolar|avro|euro|milyon|milyar|bin\b)|%\s*\d', re.I)


def leaks(text):
    """docs/n8n_routing_rule.md X: a number with a currency / scale word or a percent sign."""
    return bool(MONEY_LEAK_RE.search(text))
