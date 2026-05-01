"""
Gömrük Komitəsi hesabat faylını oxuyan modul.
Fayl formatı: ilk 7 sıra meta/başlıq, 8-ci sıra sütun adları.
Hər "səhifə"nin altında boş sıra + © footer var — onları süzgəcdən keçiririk.
"""

import pandas as pd
import re
from io import BytesIO


# Fayldakı həqiqi sütunlar → təmiz ad
COLUMN_MAP = {
    'GB sorğu nömrəsi':         'GB Sorğu Nömrəsi',
    'Bəyannamə tarixi':          'Bəyannamə Tarixi',
    'Rejim':                     'Rejim',
    'Əm\nxar':                   'Əməliyyat Xarakteri',
    'Xarici\ntərəfdaş':          'Xarici Tərəfdaş',
    'Malın adı':                 'Malın Adı',
    'Malın kodu':                'Malın Kodu (HS)',
    'Malın miqdarı':             'Malın Miqdarı',
    'Netto çəki\n(kq)':          'Netto Çəki (kq)',
    'Statistik dəyər\n(ABŞ dol.)': 'Statistik Dəyər (USD)',
    'Gömrük yığımı (AZN)':       'Gömrük Yığımı (AZN)',
    'İdxal rüsumu (AZN)':        'İdxal Rüsumu (AZN)',
    'Aksiz (AZN)':               'Aksiz (AZN)',
    'ƏDV\n(AZN)':                'ƏDV (AZN)',
    'Digər yığımlar (AZN)':      'Digər Yığımlar (AZN)',
}


def read_gomruk_file(file) -> tuple[pd.DataFrame, dict]:
    """
    Gömrük hesabat faylını oxuyur.
    Returns:
        df   — təmiz DataFrame
        meta — {voen, shirket, dovr} məlumatları
    """
    raw = pd.read_excel(file, header=None)

    # Meta məlumatları (ilk 7 sıra)
    meta = _extract_meta(raw)

    # Başlıq sırasını tap (GB sorğu nömrəsi)
    header_row = _find_header_row(raw)

    # Faylı düzgün oxu
    if hasattr(file, 'seek'):
        file.seek(0)
    df_raw = pd.read_excel(file, header=header_row)

    # Lazımlı sütunları seç
    available = {k: v for k, v in COLUMN_MAP.items() if k in df_raw.columns}
    df = df_raw[list(available.keys())].copy()
    df.rename(columns=available, inplace=True)

    # Yalnız real bəyannamə sətirləri (14 rəqəmli GB nömrəsi)
    gb_col = 'GB Sorğu Nömrəsi'
    df = df[df[gb_col].astype(str).str.match(r'^\d{14}$', na=False)].copy()

    # Malın adından \n sil
    if 'Malın Adı' in df.columns:
        df['Malın Adı'] = df['Malın Adı'].astype(str).str.replace(r'\n', ' ', regex=True).str.strip()

    # Xarici tərəfdaşdan artıq mətn sil
    if 'Xarici Tərəfdaş' in df.columns:
        df['Xarici Tərəfdaş'] = df['Xarici Tərəfdaş'].astype(str).str.replace(r'\n', ' ', regex=True).str.strip()

    df.reset_index(drop=True, inplace=True)
    return df, meta


def _extract_meta(raw: pd.DataFrame) -> dict:
    """İlk 10 sıradakı meta məlumatları çıxarır."""
    meta = {'voen': '', 'shirket': '', 'dovr': ''}
    for i in range(min(10, len(raw))):
        row_str = ' '.join(str(v) for v in raw.iloc[i] if pd.notna(v))
        if 'VÖEN' in row_str or 'VOEN' in row_str.upper():
            m = re.search(r'VÖEN[^\d]*(\d+)', row_str, re.IGNORECASE)
            if m:
                meta['voen'] = m.group(1)
        if 'Hesabat dövrü' in row_str or 'dövr' in row_str.lower():
            m = re.search(r'(\d{2}\.\d{2}\.\d{4})[^\d]+(\d{2}\.\d{2}\.\d{4})', row_str)
            if m:
                meta['dovr'] = f"{m.group(1)} – {m.group(2)}"
        # Şirkət adı (böyük hərfli, dırnaq içində)
        m = re.search(r'"([^"]+)"', row_str)
        if m and len(m.group(1)) > 5:
            meta['shirket'] = m.group(1)
    return meta


def _find_header_row(raw: pd.DataFrame) -> int:
    """'GB sorğu nömrəsi' olan sıranın indeksini tapır."""
    for i in range(min(15, len(raw))):
        row_vals = [str(v) for v in raw.iloc[i] if pd.notna(v)]
        if any('GB sorğu' in v or 'Bəyannamə' in v for v in row_vals):
            return i
    return 7  # default


def get_clean_columns(df: pd.DataFrame) -> list[str]:
    """Yalnız məlumat olan sütunları qaytarır."""
    return [c for c in df.columns if not df[c].isna().all()]
