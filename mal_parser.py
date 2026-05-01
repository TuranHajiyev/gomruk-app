"""
Gömrük hesabatının "Malın adı" sütununu parçalayan modul.
parse_mal(metn) → [{'Malın Adı': ..., 'Ölçü Vahidi': ..., 'Miqdar': ...}, ...]

Dəstəklənən formatlar:
  Format 1 — "1:MAL - 500 əd., / 200 kq MAL2 - 300 əd., 2:YIWU..."
  Format 2 — "1. Malın adı ... 2. Miqdar X yer/m2 ..."
  Format 3 — "mal adı 27380 ədəd"
  Format 4 — "1.MAL 2.Şirkət 3.Mənşə 4.Miqdar:X əd"  (GLOBAL DENPA tipi)
  Format 5 — "1.Mal 2.Şirkət 3.MƏHSUL - 143800ədəd"  (IRAN tipi)
"""

import re


def clean_company(text: str) -> str:
    """Şirkət adı, invoys, istehsalçı qeydlərini mətnden silir."""
    text = re.sub(r'\s*2:[A-ZƏÜÖĞIŞÇa-züöğışçə].*$', '', text, flags=re.DOTALL)
    text = re.sub(r'\s*invoys üzrə.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\s*[34]\.\s*(İstehsalçı|Miqdar|ölkə).*$', '', text,
                  flags=re.IGNORECASE | re.DOTALL)
    return text.strip().strip('.,').strip()


def _norm_vahid(v: str) -> str:
    return 'ədəd' if v.lower() in ('əd', 'ədəd') else v.lower()


def parse_mal(raw_text: str) -> list[dict]:
    """
    Malın adı mətnini parçalayır.
    Qaytarır: [{'Malın Adı': str, 'Ölçü Vahidi': str, 'Miqdar': str}]
    """
    text = str(raw_text).replace('\n', ' ').strip()
    results = []

    # ── Format 1: "1:MAL - miqdar əd.," ──────────────────────────
    if re.match(r'^\s*1:', text):
        clean = re.sub(r'^\s*1:\s*', '', clean_company(text))
        pat = (r'([A-ZƏÜÖĞIŞÇa-züöğışçə(][^-]+?)'
               r'\s*-\s*([\d.,]+)\s*(ədəd|əd|kq|m2|m3|yer|cüt)[.,]?'
               r'\s*(?:/\s*[\d.,]+\s*kq)?\s*')
        for m in re.finditer(pat, clean, re.IGNORECASE):
            ad = re.sub(r'^kq\s+', '', m.group(1).strip().strip('-').strip())
            if ad:
                results.append({'Malın Adı': ad,
                                'Ölçü Vahidi': _norm_vahid(m.group(3)),
                                'Miqdar': m.group(2).replace(',', '.')})
        if results:
            return results

    # ── Format 2: "1. Malın adı ... 2. Miqdar ..." ───────────────
    if re.match(r'^\s*1\.', text) and 'Malın adı' in text:
        ad_m = re.search(r'1\.\s*Malın adı\s+(.+?)(?=\s*2\.|$)', text, re.IGNORECASE)
        mq_m = re.search(r'2\.\s*Miqdar\s+([\d.,/]+)\s*(ədəd|əd|kq|m2|m3|yer|cüt)',
                         text, re.IGNORECASE)
        ad = ad_m.group(1).strip() if ad_m else clean_company(text)
        miqdar = mq_m.group(1).split('/')[0].strip() if mq_m else ''
        vahid = _norm_vahid(mq_m.group(2)) if mq_m else ''
        results.append({'Malın Adı': ad, 'Ölçü Vahidi': vahid, 'Miqdar': miqdar})
        return results

    # ── Format 4: "1.MAL 2.Şirkət... 4.Miqdar:X əd" ─────────────
    if re.match(r'^\s*1\.', text) and re.search(r'[Mm]iqdar', text):
        ad_m = re.match(r'^\s*1\.(.+?)\s*2\.', text)
        mq_m = re.search(r'[Mm]iqdar[:\s]+([\d.,]+)\s*(ədəd|əd|kq|m2|m3|m|yer|cüt|rulon)',
                         text)
        ad = ad_m.group(1).strip() if ad_m else clean_company(text)
        miqdar = mq_m.group(1).replace(',', '.') if mq_m else ''
        vahid = _norm_vahid(mq_m.group(2)) if mq_m else ''
        results.append({'Malın Adı': ad, 'Ölçü Vahidi': vahid, 'Miqdar': miqdar})
        return results

    # ── Format 5: "1.Mal 2.Şirkət 3.MƏHSUL - 143800ədəd" ────────
    if re.match(r'^\s*1\.', text) and re.search(r'\d+ədəd|\d+\s*əd\b', text):
        ad_m = re.match(r'^\s*1\.(.+?)\s*2\.', text)
        mq_m = re.search(r'([\d.,]+)\s*(ədəd|əd)', text)
        ad = ad_m.group(1).strip() if ad_m else clean_company(text)
        results.append({'Malın Adı': ad, 'Ölçü Vahidi': 'ədəd',
                        'Miqdar': mq_m.group(1) if mq_m else ''})
        return results

    # ── Format 3: "mal adı 27380 ədəd" ───────────────────────────
    m = re.match(r'^(.+?)\s+([\d.,]+)\s*(ədəd|əd|kq|m2|m3|yer|cüt)', text, re.IGNORECASE)
    if m:
        results.append({'Malın Adı': m.group(1).strip(),
                        'Ölçü Vahidi': _norm_vahid(m.group(3)),
                        'Miqdar': m.group(2).replace(',', '.')})
        return results

    # Heç format uyğun gəlmədi — mətni təmizlə, saxla
    results.append({'Malın Adı': clean_company(text), 'Ölçü Vahidi': '', 'Miqdar': ''})
    return results
