"""
Gömrük Ödənişlərinin Uyğunlaşdırılması Modulu.
"""

import streamlit as st
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from io import BytesIO


def _to_float(val):
    if val is None: return 0.0
    s = str(val).replace(' ', '').replace(',', '.').strip()
    try: return float(s)
    except: return 0.0


def parse_file(file_bytes):
    wb   = load_workbook(BytesIO(file_bytes), data_only=True)
    ws   = wb.active
    rows = list(ws.iter_rows(values_only=True))
    meta = {'shirket': '', 'dovr': ''}
    madaxil_rows = []
    mexaric_rows = []
    mode = None

    for row in rows:
        cells = {j: (str(v).strip() if v is not None else '') for j, v in enumerate(row)}
        line  = ' '.join(cells.values())

        for v in cells.values():
            if ('Məhdud' in v or 'MMC' in v or 'ASC' in v) and not meta['shirket']:
                meta['shirket'] = v.split('\n')[0].strip()
            if 'dən' in v and 'dək' in v and '-' in v and not meta['dovr']:
                meta['dovr'] = v.strip()

        if 'Mədaxil' in line and 'Məxaric' not in line and len(line.strip()) < 50:
            mode = 'madaxil'; continue
        if 'Məxaric' in line and len(line.strip()) < 50:
            mode = 'mexaric'; continue
        if '©' in line or 'Dövrün' in line or 'Hesabat dövrü' in line: continue
        if 'Əməliyyat tarixi' in line or 'Hesab Tarixi' in line: continue

        if mode == 'madaxil':
            tarix    = cells.get(3,'') or cells.get(4,'')
            qebz     = cells.get(11,'') or cells.get(12,'')
            teyinat  = cells.get(14,'') or cells.get(15,'')
            nov      = cells.get(18,'') or cells.get(19,'')
            meblег   = cells.get(22,'') or cells.get(23,'')
            odenilib = (cells.get(32,'') or cells.get(33,'')).strip()
            if tarix and teyinat and meblег:
                madaxil_rows.append({
                    'Tarix': tarix, 'Qəbz': qebz,
                    'Ödənişin Təyinatı': teyinat, 'Növ': nov,
                    'Məbləğ': _to_float(meblег), 'Status': odenilib
                })

        elif mode == 'mexaric':
            tarix = cells.get(1,'')
            hesab = cells.get(9,'')
            emel  = cells.get(13,'')
            mebl  = cells.get(17,'')
            beyan = cells.get(20,'')
            if tarix and emel and mebl and beyan:
                mexaric_rows.append({
                    'Tarix': tarix, 'Hesab': hesab,
                    'Əməliyyat Növü': emel,
                    'Məbləğ': _to_float(mebl),
                    'Bəyannamə': beyan.strip()
                })

    return pd.DataFrame(madaxil_rows), pd.DataFrame(mexaric_rows), meta


# Hesab → Təyinat uyğunluq xəritəsi
HESAB_MAP = {
    'ƏDV depozit':         ['ƏDV'],
    'Avans':               ['Avans'],
    'Xidmətlər':           ['Xidmətlər', 'Xidmətlər üzrə ƏDV'],
    'Xidmətlər üzrə ƏDV': ['Xidmətlər', 'Xidmətlər üzrə ƏDV'],
}

def _mexaric_for(teyinat, mexaric_df):
    """Bu mədaxil təyinatına uyğun məxaric sətirləri tap."""
    for hesab, teyinatlar in HESAB_MAP.items():
        if teyinat in teyinatlar:
            sub = mexaric_df[mexaric_df['Hesab'] == hesab]
            if not sub.empty:
                return sub
    # Fallback: əməliyyat növündə axtar
    return mexaric_df[
        mexaric_df['Əməliyyat Növü'].str.contains(teyinat, case=False, na=False)
    ]


def build_uygun_rows(madaxil_df, mexaric_df, yalniz_odenilib):
    """
    Nəticə: hər mədaxil üçün bir "başlıq" sətri + altında məxaric sətirləri + cəm sətri.
    Çıxış sütunları: tip | Ödənişin Təyinatı | Ödənilən Məbləğ | Silinən Məbləğ | Bəyannamə
    """
    src = madaxil_df.copy()
    if yalniz_odenilib:
        src = src[src['Status'] == 'Ödənilib']

    result = []

    for _, mad in src.iterrows():
        teyinat   = mad['Ödənişin Təyinatı']
        odeniyen  = mad['Məbləğ']
        qebz      = mad['Qəbz']
        tarix     = mad['Tarix']

        mexaric_sub = _mexaric_for(teyinat, mexaric_df).copy()
        mx_sum      = mexaric_sub['Məbləğ'].sum()
        ferq        = round(odeniyen - mx_sum, 2)
        uygun       = abs(ferq) < 0.02

        # Başlıq sətri — mədaxil
        result.append({
            '_tip':               'madaxil',
            'Tarix':              tarix,
            'Qəbz':               qebz,
            'Ödənişin Təyinatı':  teyinat,
            'Ödənilən Məbləğ':    odeniyen,
            'Silinən Məbləğ':     None,
            'Bəyannamə':          '',
            'Əməliyyat Növü':     '',
            'Uyğunluq':           '✅' if uygun else '⚠️',
        })

        # Məxaric sətirləri
        for _, mx in mexaric_sub.iterrows():
            result.append({
                '_tip':               'mexaric',
                'Tarix':              mx['Tarix'],
                'Qəbz':               '',
                'Ödənişin Təyinatı':  '',
                'Ödənilən Məbləğ':    None,
                'Silinən Məbləğ':     mx['Məbləğ'],
                'Bəyannamə':          mx['Bəyannamə'],
                'Əməliyyat Növü':     mx['Əməliyyat Növü'],
                'Uyğunluq':           '',
            })

        # Cəm sətri
        result.append({
            '_tip':               'cem',
            'Tarix':              '',
            'Qəbz':               '',
            'Ödənişin Təyinatı':  'Cəmi:',
            'Ödənilən Məbləğ':    odeniyen,
            'Silinən Məbləğ':     round(mx_sum, 2),
            'Bəyannamə':          f"Fərq: {ferq:+.2f}" if not uygun else '',
            'Əməliyyat Növü':     '',
            'Uyğunluq':           '✅ Uyğun' if uygun else f'⚠️ Fərq: {ferq:+.2f}',
        })

    return pd.DataFrame(result)


def to_excel_bytes(df):
    """Qruplaşdırılmış cədvəli Excel-ə yaz."""
    wb = load_workbook(BytesIO(b''))  # boş
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Uyğunlaşdırma'

    thin = Side(style='thin', color='CCCCCC')
    brd  = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Başlıqlar
    headers = ['Tarix', 'Ödənişin Təyinatı', 'Əməliyyat Növü',
               'Ödənilən Məbləğ', 'Silinən Məbləğ', 'Bəyannamə', 'Uyğunluq']
    hdr_fill = PatternFill('solid', fgColor='1F4E79')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = hdr_font; c.fill = hdr_fill
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = brd
    ws.row_dimensions[1].height = 24

    mad_fill = PatternFill('solid', fgColor='1F4E79')  # tünd mavi — mədaxil
    mex_fill = PatternFill('solid', fgColor='EBF3FB')  # açıq — məxaric
    cem_fill = PatternFill('solid', fgColor='D6E4F0')  # orta — cəm

    ri = 2
    for _, row in df.iterrows():
        tip = row['_tip']
        vals = [
            row['Tarix'],
            row['Ödənişin Təyinatı'],
            row['Əməliyyat Növü'],
            row['Ödənilən Məbləğ'],
            row['Silinən Məbləğ'],
            row['Bəyannamə'],
            row['Uyğunluq'],
        ]
        fill = mad_fill if tip=='madaxil' else (cem_fill if tip=='cem' else mex_fill)
        font_color = 'FFFFFF' if tip=='madaxil' else '000000'

        for ci, val in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.fill   = fill
            c.font   = Font(bold=(tip in ('madaxil','cem')), color=font_color, size=10)
            c.border = brd
            c.alignment = Alignment(vertical='center')
            if isinstance(val, float) and val is not None:
                c.number_format = '#,##0.00'
        ri += 1

    # Sütun enləri
    widths = [22, 22, 22, 16, 16, 18, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def show():
    st.header("💳 Gömrük Ödənişlərinin Uyğunlaşdırılması")
    st.caption("Mədaxil ödənişlərini məxaric bəyannamə silmələri ilə uyğunlaşdırır.")

    uploaded = st.file_uploader(
        "Avans hesabı çıxarışını yükləyin (.xlsx)",
        type=["xlsx"], key="odenis_uploader"
    )
    if not uploaded:
        st.info("Gömrük Komitəsinin avans hesabı çıxarışını yükləyin.")
        return

    file_bytes = uploaded.read()
    with st.spinner("Fayl oxunur..."):
        try:
            madaxil_df, mexaric_df, meta = parse_file(file_bytes)
        except Exception as e:
            st.error(f"Fayl oxunarkən xəta: {e}")
            return

    if meta.get('shirket'):
        st.info(f"🏢 **{meta['shirket']}**  |  📅 {meta.get('dovr','')}")

    c1, c2, c3, c4 = st.columns(4)
    odenilib_cem = madaxil_df[madaxil_df['Status']=='Ödənilib']['Məbləğ'].sum()
    c1.metric("Mədaxil sətiri",    len(madaxil_df))
    c2.metric("Məxaric sətiri",    len(mexaric_df))
    c3.metric("Ödənilib cəmi",     f"{odenilib_cem:,.2f} AZN")
    c4.metric("Məxaric cəmi",      f"{mexaric_df['Məbləğ'].sum():,.2f} AZN")

    st.divider()

    yalniz_odenilib = st.toggle(
        "Yalnız **Ödənilib** işarəlilər",
        value=True,
        help="Aktiv: yalnız 'Ödənilib' sütunu dolub olanlar. Deaktiv: bütün mədaxillər."
    )

    with st.spinner("Uyğunlaşdırılır..."):
        df = build_uygun_rows(madaxil_df, mexaric_df, yalniz_odenilib)

    if df.empty:
        st.warning("Uyğunlaşdırılacaq məlumat tapılmadı.")
        return

    # Göstərmə sütunları (_tip sütununu gizlət)
    show_cols = ['Tarix','Ödənişin Təyinatı','Əməliyyat Növü',
                 'Ödənilən Məbləğ','Silinən Məbləğ','Bəyannamə','Uyğunluq']

    def highlight(row):
        tip = df.loc[row.name, '_tip']
        if tip == 'madaxil':
            return ['background-color:#1F4E79;color:white;font-weight:bold'] * len(row)
        elif tip == 'cem':
            return ['background-color:#D6E4F0;font-weight:bold'] * len(row)
        else:
            return ['background-color:#EBF3FB'] * len(row)

    st.dataframe(
        df[show_cols].style.apply(highlight, axis=1),
        use_container_width=True,
        height=500
    )

    # Statistika
    cem_rows = df[df['_tip']=='cem']
    uygun    = (cem_rows['Uyğunluq'].str.startswith('✅')).sum()
    ferqli   = (cem_rows['Uyğunluq'].str.startswith('⚠️')).sum()
    st.caption(f"✅ Uyğun: **{uygun}** | ⚠️ Fərq var: **{ferqli}**")

    st.divider()
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥 Excel kimi yüklə",
            data=to_excel_bytes(df),
            file_name="odenis_uygunlasma.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary"
        )
    with dl2:
        csv = df[show_cols].to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📄 CSV kimi yüklə",
            data=csv,
            file_name="odenis_uygunlasma.csv",
            mime="text/csv",
            use_container_width=True
        )
