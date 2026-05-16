"""
Gömrük hesabatının "Malın adı" sütununu parçalayan modul.
parse_mal(metn) → [{'Malın Adı': str, 'Ölçü Vahidi': str, 'Miqdar': str}]
"""

import re

NUM   = r'[\d]+(?:[.,]\d+)?'
VAHID = r'(ədəd|əd\b|kq\b|m2\b|m3\b|yer\b|cüt\b|ton\b|rulon\b)'

# ── Təmizləmə ─────────────────────────────────────────────

_NOISE = [
    r'\s*[İi]nvoys?\s+(üzrə|mövqeyi|üzrə\s+mal\s+mövqeyi).*$',
    r'\s*[İi]nvoys?\s*mövqeyi.*$',
    r'\s*[İi]nvoyd?[aə]k[ıi]\s*mövqeyi.*$',
    r'\s*[İi][Nn][Vv][Oo][Yy][Ss]?\s+[Mm]övqeyi.*$',
    r'\s*[İi][Nn][Vv][Oo][İi][Cc][Ee]?\s+[Nn]\s*\d+.*$',
    r'\s*2\s*:\s*[A-ZƏÜÖĞIŞÇa-züöğışçə].*$',
    r'\s*[İi]stehsalçı.*$',
    r'\s*[34]\.\s*(İstehsalçı|Miqdar|ölkə|Ticarət).*$',
    r'\s*Ticarət\s+edən.*$',
    r'\s*Mənşə\s*:.*$',
    r'\s*Model\s*:.*$',
    r'\s*Cəmi\s*:.*$',
    r'\s*INVOICE\s+N.*$',
]

def _strip_noise(text):
    text = re.sub(r'^\s*[Mm]al[ıi]n\s+ad[ıi]\s*[-:]\s*', '', text)
    text = re.sub(r'^\s*[Mm]al[ıi]n\s+ad[ıi]\s+', '', text)
    for p in _NOISE:
        text = re.sub(p, '', text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()

def _clean(name):
    """Ad sonundakı lazımsız simvolları sil."""
    name = name.strip()
    # "kg " və ya "kq " prefiksi (çoxlu mal ayırıcısından qalan)
    name = re.sub(r'^k[qg]\s+', '', name, flags=re.IGNORECASE)
    # "yer N" və ya "yer N," sonunda → sil
    name = re.sub(r'\s+yer\s+\d+[\s,]*$', '', name, flags=re.IGNORECASE)
    # Sondakı - / . , ; boşluqlar
    name = re.sub(r'[\s\-/.,;:]+$', '', name)
    # Əvvəldəki "N." və ya "N:" prefiksi (1. 2. 1: 2:)
    name = re.sub(r'^\s*\d+\s*[.:]\s*', '', name)
    # Əvvəldəki tire
    name = re.sub(r'^\s*[-–]\s*', '', name)
    return name.strip()

def _vahid(v):
    v = (v or '').strip().lower()
    return 'ədəd' if v in ('əd', 'ədəd') else v

def _row(name, vahid='', miqdar=''):
    return {
        'Malın Adı':   _clean(name),
        'Ölçü Vahidi': _vahid(vahid),
        'Miqdar':      str(miqdar).replace(',', '.') if miqdar else ''
    }


# ── Format funksiyaları ───────────────────────────────────

def _f_invoice_caps(text):
    """
    "1.ƏTİR QABI 30240 ƏDƏD / KQ- İNVOİCE N 1  2.ŞÜŞƏ BUTULKA 600 ƏDƏD/ KQ-İNVOİCE N 3"
    İNVOİCE N X ilə bloklara bölür.
    """
    if not re.search(r'İNVOİCE|INVOICE', text, re.IGNORECASE):
        return []
    blocks = re.split(r'-?\s*(?:İNVOİCE|INVOICE)\s+N\s*\d+\s*', text, flags=re.IGNORECASE)
    results = []
    for block in blocks:
        block = re.sub(r'^\s*\d+\.\s*', '', block.strip())
        if not block:
            continue
        m = re.match(
            r'^([A-ZƏÜÖĞIŞÇa-züöğışçə].+?)\s+(' + NUM + r')\s+(ƏDƏD|ƏD|əd|ədəd)\b',
            block, re.IGNORECASE)
        if m:
            results.append(_row(m.group(1), 'ədəd', m.group(2)))
    return results


def _f_bolt(text):
    """
    "1:BOLT 173qutu/54960əd.,/4761kq"
    "1:ŞRUP 1189qutu/25830 əd.,/16256kq"
    """
    m = re.match(
        r'^\s*1\s*:\s*([A-ZƏÜÖĞIŞÇa-züöğışçə\s]+?)'
        r'\s+\d+\s*qutu\s*/\s*(' + NUM + r')\s*(əd|ədəd)',
        text, re.IGNORECASE)
    if m:
        return [_row(m.group(1), 'ədəd', m.group(2))]
    return []


def _f1_colon(text):
    """
    "1:MAL - 900 əd., / 134 kq  MAL2 - 300 əd.,"
    """
    if not re.match(r'^\s*1\s*:', text):
        return []
    clean = _strip_noise(text)
    clean = re.sub(r'^\s*1\s*:\s*', '', clean)
    pat = (r'([A-ZƏÜÖĞIŞÇa-züöğışçə"\(][^-]*?)'
           r'\s*-\s*(' + NUM + r')\s*' + VAHID + r'[.,]?'
           r'(?:\s*/\s*' + NUM + r'\s*kq)?')
    results = []
    for m in re.finditer(pat, clean, re.IGNORECASE):
        ad = re.sub(r'^kq\s+', '', m.group(1).strip())
        results.append(_row(ad, m.group(3), m.group(2)))
    return results


def _f2_mal_adi(text):
    """
    "1. Malın adı XXX 2. Miqdar N yer/m2"
    """
    if not (re.match(r'^\s*1\.', text) and re.search(r'[Mm]al[\u0131i]n\s+ad[\u0131i]', text)):
        return []
    ad_m = re.search(r'1\.\s*[Mm]al[\u0131i]n\s+ad[\u0131i][-\s]+(.+?)(?=\s*2\.|$)', text)
    ad   = ad_m.group(1).strip() if ad_m else _strip_noise(text)
    # Miqdar + vahid axtarışı — vahid olmaya da bilər
    miq_m = re.search(
        r'2\.\s*[Mm]iqdar\s+([\d]+(?:[.,]\d+)?)(?:\s*yer/)?(?:\s*[\d]+(?:[.,]\d+)?)?\s*(\u0259d\u0259d|\u0259d\b|kq\b|m2\b|m3\b|yer\b|c\u00fct\b|ton\b)?',
        text, re.IGNORECASE)
    miqdar = miq_m.group(1) if miq_m else ''
    vahid  = (miq_m.group(2) or 'yer') if miq_m else 'yer'
    return [_row(ad, vahid, miqdar)]

def _f3_global(text):
    """
    "1.MAL 2.Şirkət 3.Mənşə 4.Ümumi miqdar:N / 4.Miqdar:N"
    """
    if not re.match(r'^\s*1\.', text):
        return []
    if re.search(r'[Mm]al[\u0131i]n\s+ad[\u0131i]', text):
        return []
    ad_m = re.match(r'^\s*1\.\s*(.+?)\s*2\.', text)
    if not ad_m:
        return []
    # "4.Ümumi miqdar:240 əd" və ya "4.Miqdar:240" və ya "Ümumi miqdar:240"
    miq_m = re.search(
        r'(?:[Üü]mumi\s+)?[Mm]iqdar\s*:\s*([\d]+(?:[.,]\d+)?)\s*(\u0259d\u0259d|\u0259d\b|kq\b|m2\b|m3\b|yer\b)?',
        text, re.IGNORECASE)
    miqdar = miq_m.group(1) if miq_m else ''
    vahid  = (miq_m.group(2) or '\u0259d\u0259d') if miq_m else '\u0259d\u0259d'
    return [_row(ad_m.group(1), vahid, miqdar)]


def _f4_iran(text):
    """
    "1.MAL 2.Şirkət 3.AD - 143800ədəd"
    """
    if not re.match(r'^\s*1\.', text):
        return []
    ad_m  = re.match(r'^\s*1\.\s*(.+?)\s*2\.', text)
    miq_m = re.search(r'(' + NUM + r')\s*(ədəd|əd)\b', text, re.IGNORECASE)
    if not ad_m or not miq_m:
        return []
    return [_row(ad_m.group(1), 'ədəd', miq_m.group(1))]


def _f5_yer(text):
    """
    "MAL yer N, SAYI əd, KQ  MAL2 yer N, SAYI əd, KQ invoys..."
    "PLASTİK LAPATKA yer 20, 750 əd, 394 kg invoys..."
    """
    clean = _strip_noise(text)
    # Çoxlu mal: "MAL yer N, SAYI əd," tipli
    multi = re.findall(
        r'([A-ZƏÜÖĞIŞÇa-züöğışçə][A-ZƏÜÖĞIŞÇa-züöğışçə\s]+?)'
        r'(?:\s+yer\s+\d+\s*,)?\s+(' + NUM + r')\s+(əd|ədəd|cüt)\s*[,.]?',
        clean, re.IGNORECASE)
    if multi:
        return [_row(m[0], m[2], m[1]) for m in multi]
    # Tək mal
    m = re.match(
        r'^([A-ZƏÜÖĞIŞÇa-züöğışçə].+?)(?:\s+yer\s+\d+\s*,)?\s+(' + NUM + r')\s+(əd|ədəd|cüt)\b',
        clean, re.IGNORECASE)
    if m:
        return [_row(m.group(1), m.group(3), m.group(2))]
    # Miqdar yoxdur — yalnız ad
    if clean:
        return [_row(clean)]
    return []


def _f6_simple(text):
    """
    "led spot lampaları-4000 ədəd / 147.6 kq, led lampalar-1000 ədəd"
    "çılçıraqlar-3933 ədəd / 11608.20 kq, bralar-1140 ədəd"
    "plastmasdan kranlar 11700 ədəd"
    """
    # Çoxlu mal: "ad-N vahid, ad2-N vahid"
    multi = re.findall(
        r'([a-zA-ZƏÜÖĞIŞÇəüöğışçÇ][^\d,]+?)'
        r'[-–\s]+(' + NUM + r')\s*' + VAHID + r'[,\s]',
        text, re.IGNORECASE)
    if len(multi) >= 2:
        return [_row(m[0], m[2], m[1]) for m in multi
                if not re.match(r'^k[qg]\b', m[0].strip(), re.IGNORECASE)]
    # Tək mal
    m = re.match(
        r'^(.+?)[-–\s]+(' + NUM + r')\s*(?:qutu/)?(?:' + NUM + r'/)?\s*' + VAHID,
        text, re.IGNORECASE)
    if m:
        return [_row(m.group(1), m.group(3), m.group(2))]
    return []


# ── Əsas funksiya ─────────────────────────────────────────

def parse_mal(raw_text: str) -> list:
    text = str(raw_text).replace('\n', ' ').replace('\t', ' ').strip()
    text = re.sub(r'\s{2,}', ' ', text)

    # 1. İNVOİCE böyük hərfli bloklar (ƏTİR QABI tipi)
    r = _f_invoice_caps(text)
    if r: return r

    # 2. BOLT/ŞRUP — "1:AD Nqutu/Məd"
    r = _f_bolt(text)
    if r: return r

    # 3. "1:MAL - N əd.,"
    r = _f1_colon(text)
    if r: return r

    # 4. "1. Malın adı ... 2. Miqdar"
    r = _f2_mal_adi(text)
    if r: return r

    # 5. "1.MAL 2.Şirkət ... 4.Miqdar:N" (GLOBAL tipi)
    r = _f3_global(text)
    if r: return r

    # 6. "1.MAL 2.Şirkət ... Nədəd" (IRAN tipi)
    r = _f4_iran(text)
    if r: return r

    # 7. "MAL yer N, SAYI əd" tipli + invoys
    if re.search(r'yer\s+\d+|invoys|mövqeyi', text, re.IGNORECASE):
        r = _f5_yer(text)
        if r: return r

    # 8. Sadə: "ad SAYI vahid" / çoxlu "ad-N vahid, ad2-N vahid"
    r = _f6_simple(text)
    if r: return r

    # 9. Heç biri uyğun gəlmədi — mətni təmizlə
    return [_row(_strip_noise(text))]
