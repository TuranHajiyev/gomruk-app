"""
Gömrük hesabatının "Malın adı" sütununu parçalayan modul.
parse_mal(metn) → [{'Malın Adı': str, 'Ölçü Vahidi': str, 'Miqdar': str}]
"""

import re

# ── Sabitlər ─────────────────────────────────────────────
VAHID_PAT = r'(ədəd|əd\b|kq\b|m2\b|m3\b|yer\b|cüt\b|ton\b|rulon\b|m\b)'
NUM_PAT   = r'[\d]+(?:[.,]\d+)?'

# Silinəcək sonluqlar — invoys, istehsalçı, şirkət adları
_STRIP_PATTERNS = [
    r'\s*[İi]nvoys\s+(üzrə|mövqeyi|üzrə\s+mal\s+mövqeyi).*$',
    r'\s*[İi]nvoyd?[aə]k[ıi]\s+mövqeyi.*$',
    r'\s*invoys?\s*mövqeyi.*$',
    r'\s*invo[yp]s?\s+mövqeyi.*$',
    r'\s*[İi]nvo[yp][cs]e?\s+[Nn]\s*\d+.*$',
    r'\s*[İi]NVOYS.*$',
    r'\s*İNVOİCE.*$',
    r'\s*[İi]nvoyv?\s+mövqeyi.*$',
    r'\s*ijnvoys.*$',
    r'\s*invpys.*$',
    r'\s*invoyys.*$',
    r'\s*2:\s*[A-ZƏÜÖĞIŞÇa-züöğışçə].*$',
    r'\s*2:\s*PARADI.*$',
    r'\s*[İi]stehsalçı.*$',
    r'\s*[34]\.\s*(İstehsalçı|Miqdar|ölkə|Ticarət).*$',
    r'\s*Ticarət edən şirkət.*$',
    r'\s*Mənşə:.*$',
    r'\s*Model:.*$',
    r'\s*Cəmi:.*$',
    r'\s*INVOICE.*$',
]

def _strip_noise(text: str) -> str:
    """Şirkət adı, invoys, istehsalçı qeydlərini silir."""
    # "Malın adı:" prefiksi
    text = re.sub(r'^\s*[Mm]alın\s+adı\s*[-:]\s*', '', text)
    text = re.sub(r'^\s*[Mm]alın\s+adı\s*', '', text)
    for pat in _STRIP_PATTERNS:
        text = re.sub(pat, '', text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def _clean_name(name: str) -> str:
    """Ad sonundakı nöqtə, vergül, slaş, yer N, boşluq sil."""
    name = name.strip()
    # "yer N," tipini sil — "TÜSTÜ VERƏN yer 4," → "TÜSTÜ VERƏN"
    name = re.sub(r'\s+yer\s+\d+\s*,?\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+yer\s+\d+\s*$', '', name, flags=re.IGNORECASE)
    # Sondakı - / . , ; boşluqları sil
    name = re.sub(r'[\s\-/.,;]+$', '', name)
    # "1." prefiksi sil (sətrin əvvəlindəki)
    name = re.sub(r'^\d+\.\s*', '', name)
    # "1:" prefiksi sil
    name = re.sub(r'^\d+:\s*', '', name)
    return name.strip()


def _norm_vahid(v: str) -> str:
    v = v.strip().lower()
    return 'ədəd' if v in ('əd', 'ədəd', 'ədəd.') else v


def _make(name, vahid='', miqdar=''):
    return {'Malın Adı': _clean_name(name),
            'Ölçü Vahidi': _norm_vahid(vahid),
            'Miqdar': str(miqdar).replace(',', '.') if miqdar else ''}


# ── Format tanıyıcılar ────────────────────────────────────

def _fmt1(text):
    """
    Format 1: "1:MAL - 900 əd., / 134 kq  MAL2 - 120 əd.,"
    və ya    "1: MAL -2000 əd.,"
    """
    if not re.match(r'^\s*1\s*:', text):
        return []
    clean = _strip_noise(text)
    clean = re.sub(r'^\s*1\s*:\s*', '', clean)

    # Hər mövqeyi ayır: AD - SAYI vahid [/ çəki kq]
    pat = (r'([A-ZƏÜÖĞIŞÇa-züöğışçə"\(][^-]*?)'
           r'\s*-\s*'
           r'({num})\s*(?:qutu/)?(?:{num})?({vahid})[.,]?\s*'
           r'(?:/\s*{num}\s*kq)?'.format(num=NUM_PAT, vahid=VAHID_PAT[1:-1]))
    matches = list(re.finditer(pat, clean, re.IGNORECASE))
    if not matches:
        return []
    results = []
    for m in matches:
        ad = re.sub(r'^kq\s+', '', m.group(1).strip())
        # "173qutu/54960" tipli — əd. sayını götür
        miq_raw = m.group(2)
        vahid   = m.group(3)
        # "BOLT 173qutu/54960əd" — böyük sayı götür
        if 'qutu' in miq_raw.lower():
            miq_raw = re.search(r'/(\d+)', miq_raw)
            miq_raw = miq_raw.group(1) if miq_raw else ''
        results.append(_make(ad, vahid, miq_raw))
    return results


def _fmt2(text):
    """
    Format 2: "1. Malın adı XXX 2. Miqdar N yer/m2"
    """
    if not (re.match(r'^\s*1\.', text) and 'Malın adı' in text):
        return []
    ad_m  = re.search(r'1\.\s*Malın adı[-\s]+(.+?)(?=\s*2\.|$)', text, re.IGNORECASE)
    miq_m = re.search(r'2\.\s*Miqdar\s+({num})\s*(?:yer/)?({num})?\s*({vahid})'.format(
                       num=NUM_PAT, vahid=VAHID_PAT[1:-1]), text, re.IGNORECASE)
    ad     = ad_m.group(1).strip() if ad_m else _strip_noise(text)
    miqdar = miq_m.group(1) if miq_m else ''
    vahid  = miq_m.group(3) if miq_m else 'yer'
    return [_make(ad, vahid, miqdar)]


def _fmt3_global(text):
    """
    Format 3: "1.MAL 2.Ticarət... 3.Mənşə... 4.Miqdar:N əd"
              "1.MAL 2.GLOBAL... 4.Ümumi miqdar:N əd"
    """
    if not re.match(r'^\s*1\.', text):
        return []
    ad_m  = re.match(r'^\s*1\.\s*(.+?)\s*2\.', text)
    miq_m = re.search(r'[Uu]mumi\s+miqdar\s*[:]\s*({num})\s*({vahid})?'.format(
                       num=NUM_PAT, vahid=VAHID_PAT[1:-1]), text, re.IGNORECASE)
    if not miq_m:
        miq_m = re.search(r'4\.\s*Miqdar\s*[:]\s*({num})\s*({vahid})?'.format(
                           num=NUM_PAT, vahid=VAHID_PAT[1:-1]), text, re.IGNORECASE)
    if not ad_m:
        return []
    ad     = ad_m.group(1).strip()
    miqdar = miq_m.group(1) if miq_m else ''
    vahid  = miq_m.group(2) if (miq_m and miq_m.lastindex >= 2 and miq_m.group(2)) else 'ədəd'
    return [_make(ad, vahid, miqdar)]


def _fmt4_iran(text):
    """
    Format 4: "1.MAL 2.IRAN CO. 3.AD - 143800ədəd(719rulon)"
    """
    if not re.match(r'^\s*1\.', text):
        return []
    ad_m  = re.match(r'^\s*1\.\s*(.+?)\s*2\.', text)
    miq_m = re.search(r'({num})\s*(ədəd|əd)\s*(?:\(\d+rulon\))?'.format(num=NUM_PAT),
                       text, re.IGNORECASE)
    if not ad_m or not miq_m:
        return []
    return [_make(ad_m.group(1), 'ədəd', miq_m.group(1))]


def _fmt5_simple(text):
    """
    Format 5: "mal adı SAYI vahid [m3]"
    Nümunə: "plastmasdan kranlar 11700 ədəd"
             "led spot lampaları-4000 ədəd / 147.6 kq"
             "çılçıraqlar-3933 ədəd / 11608.20 kq"
    Çoxlu mal: "led spot-4000 ədəd, led lamp-1000 ədəd 5000 ədəd m3"
    """
    # Çoxlu mal: "AD-N vahid, AD2-N vahid" tipli sətir
    multi_pat = (r'([a-zA-ZƏÜÖĞIŞÇəüöğışçÇ][^,\-]+?)'
                 r'[-–]\s*({num})\s*({vahid})[,\s]'.format(
                  num=NUM_PAT, vahid=VAHID_PAT[1:-1]))
    multi = list(re.finditer(multi_pat, text, re.IGNORECASE))
    if len(multi) >= 2:
        results = []
        for m in multi:
            results.append(_make(m.group(1), m.group(3), m.group(2)))
        return results

    # Tək mal: "ad-SAYI vahid" və ya "ad SAYI vahid"
    m = re.match(
        r'^(.+?)[-–\s]+({num})\s*(?:qutu/)?(?:{num}/)?\s*({vahid})'.format(
         num=NUM_PAT, vahid=VAHID_PAT[1:-1]),
        text, re.IGNORECASE)
    if m:
        return [_make(m.group(1), m.group(3), m.group(2))]
    return []


def _fmt6_invoys(text):
    """
    Format 6: "MAL SAYI əd, invoys mövqeyi-N"
              "MAL yer N, SAYI əd, ÇƏKI kg invoys..."
    Birdən çox mal: "MAL1 yer N, N1 əd, kg  MAL2 yer N, N2 əd, kg invoys..."
    """
    # Şirkət/invoys hissəsini sil
    clean = _strip_noise(text)

    # Çoxlu mal "MAL yer N, SAYI əd, ..." tipli
    multi_pat = (r'([A-ZƏÜÖĞIŞÇa-züöğışçə][A-ZƏÜÖĞIŞÇa-züöğışçə\s\(\)\"]+?)'
                 r'(?:\s+yer\s+\d+\s*,)?\s+({num})\s+(əd|ədəd|cüt)\s*[,\.]?'.format(num=NUM_PAT))
    multi = list(re.finditer(multi_pat, clean, re.IGNORECASE))
    if len(multi) >= 2:
        return [_make(m.group(1), m.group(3), m.group(2)) for m in multi]

    # Tək mal: "MAL SAYI əd,"
    m = re.match(
        r'^([A-ZƏÜÖĞIŞÇa-züöğışçə].+?)\s+({num})\s+(əd|ədəd|cüt)\s*[,\.]?'.format(num=NUM_PAT),
        clean, re.IGNORECASE)
    if m:
        return [_make(m.group(1), m.group(3), m.group(2))]

    # Miqdar yoxdur — yalnız ad var (LAQONDA invoys mövqeyi-27)
    if clean.strip():
        return [_make(clean)]
    return []


def _fmt7_invoice_caps(text):
    """
    Format 7: "1.ƏTİR QABI 30240 ƏDƏD / 5278 KQ- İNVOİCE N 1  2.ŞÜŞƏ BUTULKA 600 ƏDƏD/ 107 KQ"
    Hər "N.AD SAYI ƏDƏD ... İNVOİCE N X" blokunu ayırır.
    """
    results = []
    # "İNVOİCE N X" ayırıcı ilə bloklara böl
    blocks = re.split(r'-?\s*(?:İNVOİCE|INVOICE)\s+N\s*\d+\s*', text, flags=re.IGNORECASE)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # "N." prefiksini sil
        block = re.sub(r'^\d+\.\s*', '', block).strip()
        m = re.match(
            r'^([A-ZƏÜÖĞIŞÇa-züöğışçə].+?)\s+([\d]+(?:[.,]\d+)?)\s+(ƏDƏD|ƏD|əd|ədəd)\b',
            block, re.IGNORECASE)
        if m:
            results.append(_make(m.group(1).strip(), 'ədəd', m.group(2)))
    if results:
        return results
    # Fallback: tək mal "AD SAYI ƏDƏD" KQ olmadan
    m = re.match(r'^([A-ZƏÜÖĞIŞÇa-züöğışçə].+?)\s+([\d]+(?:[.,]\d+)?)\s+(ƏDƏD|ƏD)\b', text, re.IGNORECASE)
    if m:
        return [_make(m.group(1).strip(), 'ədəd', m.group(2))]
    return []

def _fmt8_bolt(text):
    """
    Format 8: "1:BOLT  173qutu/54960əd.,/4761kq"
              "1:ŞRUP 1189qutu/25830 əd.,/16256kq"
    """
    if not re.match(r'^\s*1\s*:', text):
        return []
    m = re.match(
        r'^\s*1\s*:\s*([A-ZƏÜÖĞIŞÇa-züöğışçə\s]+?)'
        r'\s+\d+qutu/(\d+)\s*(əd|ədəd)',
        text, re.IGNORECASE)
    if m:
        return [_make(m.group(1), m.group(3), m.group(2))]
    return []


# ── Əsas funksiya ─────────────────────────────────────────

def parse_mal(raw_text: str) -> list:
    text = str(raw_text).replace('\n', ' ').replace('\t', ' ').strip()
    text = re.sub(r'\s{2,}', ' ', text)

    # BOLT/ŞRUP tipli (qutu/əd formatı) — ən əvvəl yoxla
    r = _fmt8_bolt(text);          
    if r: return r

    # "1:MAL - N əd," tipli
    r = _fmt1(text);               
    if r: return r

    # "1. Malın adı ... 2. Miqdar"
    r = _fmt2(text);               
    if r: return r

    # İNVOİCE böyük hərflə — fmt3_global-dan qabaq, fmt1-dən sonra
    if 'İNVOİCE' in text.upper() or 'INVOICE' in text.upper():
        r = _fmt7_invoice_caps(text)
        if r and all(p['Miqdar'] for p in r): return r

    # GLOBAL DENPA / MK GROUP tipli
    r = _fmt3_global(text);        
    if r: return r

    # IRAN tipli (3.AD - Nədəd)
    r = _fmt4_iran(text);          
    if r: return r

    # "ad SAYI vahid" sadə format + çoxlu mal "ad-N vahid, ad2-N vahid"
    r = _fmt5_simple(text);        
    if r: return r

    # invoys mövqeyi tipli
    r = _fmt6_invoys(text);        
    if r: return r

    # Heç biri uyğun gəlmədi — mətni təmizlə, saxla
    clean = _strip_noise(text)
    return [_make(clean)]
