"""
Gömrük Ödənişlərinin Uyğunlaşdırılması Modulu.
"""

import streamlit as st
import pandas as pd
from openpyxl import load_workbook, Workbook
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
    madaxil_rows, mexaric_rows = [], []
    mode = None

    for row in rows:
        cells = {j: (str(v).strip() if v is not None else '') for j, v in enumerate(row)}
        line  = ' '.join(cells.values())

        for v in cells.values():
            if ('Məhdud' in v or 'MMC' in v or 'ASC' in v) and not meta['shirket']:
                meta['shirket'] = v.split('\n')[0].strip()
            if 'dən' in v and 'dək' in v and not meta['dovr']:
                meta['dovr'] = v.strip()

        if 'Mədaxil' in line and 'Məxaric' not in line and len(line.strip()) < 50:
            mode = 'madaxil'; continue
        if 'Məxaric' in line and len(line.strip()) < 50:
            mode = 'mexaric'; continue
        if '©' in line or 'Dövrün' in line or 'Hesabat dövrü' in line: continue
        if 'Əməliyyat tarixi' in line or 'Hesab Tarixi' in line: continue

        if mode == 'madaxil':
            tarix   = cells.get(3,'') or cells.get(4,'')
            qebz    = cells.get(11,'') or cells.get(12,'')
            teyinat = cells.get(14,'') or cells.get(15,'')
            nov     = cells.get(18,'') or cells.get(19,'')
            mebl    = cells.get(22,'') or cells.get(23,'')
            odenilib= (cells.get(32,'') or cells.get(33,'')).strip()
            if tarix and teyinat and mebl:
                madaxil_rows.append({
                    'tarix': tarix, 'qebz': qebz, 'teyinat': teyinat,
                    'nov': nov, 'mebl': _to_float(mebl), 'odenilib': odenilib
                })

        elif mode == 'mexaric':
            tarix = cells.get(1,'')
            hesab = cells.get(9,'')
            emel  = cells.get(13,'')
            mebl  = cells.get(17,'')
            beyan = cells.get(20,'')
            if tarix and emel and mebl and beyan:
                mexaric_rows.append({
                    'tarix': tarix, 'hesab': hesab, 'emel': emel,
                    'mebl': _to_float(mebl), 'beyan': beyan.strip()
                })

    return pd.DataFrame(madaxil_rows), pd.DataFrame(mexaric_rows), meta


def uygunlasdir(madaxil_df, mexaric_df, yalniz_odenilib):
    """
    Hər mədaxil qəbzini məxaric sətirləri ilə ardıcıl uyğunlaşdırır.
    Eyni hesab növündən olan məxariclər vaxt sırasına görə bölüşdürülür.
    """
    src = madaxil_df.copy()
    if yalniz_odenilib:
        src = src[src['odenilib'] == 'Ödənilib'].copy()
    if src.empty:
        return []

    # Hər hesab növü üçün məxaric sətirləri — vaxt sırasına görə
    # Mədaxil hesab → Məxaric hesab uyğunluğu
    hesab_map = {
        'Avans':               'Avans',
        'Xidmətlər':           'Xidmətlər',
        'Xidmətlər üzrə ƏDV': 'Xidmətlər',
        'ƏDV':                 'ƏDV depozit',
    }

    # Məxaric sətirləri hesab üzrə qruplaşdır, indeks sax
    mexaric_by_hesab = {}
    for hesab in mexaric_df['hesab'].unique():
        sub = mexaric_df[mexaric_df['hesab'] == hesab].copy().reset_index(drop=True)
        mexaric_by_hesab[hesab] = {'df': sub, 'used': [False]*len(sub)}

    # Hər mədaxil üçün məxaric götür
    results = []
    for _, mad in src.iterrows():
        teyinat      = mad['teyinat']
        hedef_hesab  = hesab_map.get(teyinat, teyinat)
        mad_mebl     = mad['mebl']
        qalan        = mad_mebl

        mexaric_rows_for_mad = []

        if hedef_hesab in mexaric_by_hesab:
            pool = mexaric_by_hesab[hedef_hesab]
            for i, mx_row in pool['df'].iterrows():
                if pool['used'][i]: continue
                if qalan <= 0.001: break
                mx_mebl = mx_row['mebl']
                gotur   = min(mx_mebl, qalan)
                mexaric_rows_for_mad.append({
                    'tarix': mx_row['tarix'],
                    'emel':  mx_row['emel'],
                    'mebl':  round(gotur, 2),
                    'beyan': mx_row['beyan'],
                })
                pool['used'][i] = True
                qalan -= gotur

        mx_sum  = sum(r['mebl'] for r in mexaric_rows_for_mad)
        uygun   = abs(mad_mebl - mx_sum) < 0.02

        results.append({
            'madaxil': {
                'tarix':    mad['tarix'],
                'qebz':     mad['qebz'],
                'teyinat':  teyinat,
                'mebl':     mad_mebl,
                'odenilib': mad['odenilib'],
            },
            'mexaric': mexaric_rows_for_mad,
            'mx_sum':  round(mx_sum, 2),
            'uygun':   uygun,
            'ferq':    round(mad_mebl - mx_sum, 2),
        })

    return results


def build_html(groups):
    """Qruplaşdırılmış uyğunlaşdırmanı HTML cədvəl kimi göstər."""
    headers = ['Tarix', 'Ödənişin Təyinatı', 'Əməliyyat Növü',
               'Ödənilən Məbləğ', 'Silinən Məbləğ', 'Bəyannamə', '']

    th = ''.join(
        f'<th style="padding:7px 12px;background:#0F2D4A;color:white;'
        f'border:1px solid #2a5080;white-space:nowrap">{h}</th>'
        for h in headers
    )

    tbody = ''
    for g in groups:
        mad    = g['madaxil']
        mex_l  = g['mexaric']
        mx_sum = g['mx_sum']
        uygun  = g['uygun']
        ferq   = g['ferq']

        def td(val, bold=False, right=False, color='inherit'):
            style = (f'padding:5px 12px;border:1px solid #ccc;'
                     f'text-align:{"right" if right else "left"};'
                     f'font-weight:{"bold" if bold else "normal"};color:{color}')
            v = f'{val:,.2f}' if isinstance(val, float) else (val or '')
            return f'<td style="{style}">{v}</td>'

        # Mədaxil başlıq sətri — tünd mavi
        uyq_icon = '✅' if uygun else f'⚠️ {ferq:+.2f}'
        tbody += (
            f'<tr style="background:#1F4E79;color:white">'
            f'{td(mad["tarix"], bold=True)}'
            f'{td(mad["teyinat"], bold=True)}'
            f'{td("")}'
            f'{td(mad["mebl"], bold=True, right=True, color="white")}'
            f'{td("")}'
            f'{td("")}'
            f'{td(uyq_icon, bold=True, color="white")}'
            f'</tr>'
        )

        # Məxaric sətirləri — açıq mavi
        for mx in mex_l:
            tbody += (
                f'<tr style="background:#EBF3FB;color:#111">'
                f'{td(mx["tarix"])}'
                f'{td("")}'
                f'{td(mx["emel"])}'
                f'{td("")}'
                f'{td(mx["mebl"], right=True)}'
                f'{td(mx["beyan"])}'
                f'{td("")}'
                f'</tr>'
            )

        # Cəm sətri — orta mavi
        ferq_str = '' if uygun else f'Fərq: {ferq:+.2f}'
        tbody += (
            f'<tr style="background:#D6E4F0;color:#1F4E79;font-weight:bold">'
            f'{td("Cəmi:", bold=True)}'
            f'{td("")}{td("")}'
            f'{td(mad["mebl"], bold=True, right=True)}'
            f'{td(mx_sum, bold=True, right=True)}'
            f'{td(ferq_str, color="#c0392b" if ferq_str else "inherit")}'
            f'{td("")}'
            f'</tr>'
        )
        # Boş ayırıcı sətir
        tbody += f'<tr><td colspan="7" style="height:6px;background:#f0f4f8"></td></tr>'

    return f'''
    <div style="overflow-x:auto">
    <table style="border-collapse:collapse;width:100%;font-size:13px;font-family:Arial,sans-serif">
    <thead><tr>{th}</tr></thead>
    <tbody>{tbody}</tbody>
    </table></div>'''


def to_excel_bytes(groups):
    """Nəticəni Excel-ə yaz."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Uyğunlaşdırma'

    thin = Side(style='thin', color='CCCCCC')
    brd  = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = ['Tarix','Ödənişin Təyinatı','Əməliyyat Növü',
               'Ödənilən Məbləğ','Silinən Məbləğ','Bəyannamə','Uyğunluq']
    fills = {
        'h':   PatternFill('solid', fgColor='0F2D4A'),
        'mad': PatternFill('solid', fgColor='1F4E79'),
        'mex': PatternFill('solid', fgColor='EBF3FB'),
        'cem': PatternFill('solid', fgColor='D6E4F0'),
    }

    # Başlıq
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = fills['h']
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = brd
    ws.row_dimensions[1].height = 24

    ri = 2
    def write_row(vals, fill_key, bold=False, white_text=False):
        nonlocal ri
        f = fills[fill_key]
        fc = 'FFFFFF' if white_text else '111111'
        for ci, val in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.fill = f
            c.font = Font(bold=bold, color=fc, size=10)
            c.border = brd
            c.alignment = Alignment(vertical='center',
                                    horizontal='right' if ci in (4,5) else 'left')
            if isinstance(val, float):
                c.number_format = '#,##0.00'
        ri += 1

    for g in groups:
        mad   = g['madaxil']
        uyq   = '✅ Uyğun' if g['uygun'] else f"⚠️ Fərq: {g['ferq']:+.2f}"
        write_row([mad['tarix'], mad['teyinat'], '', mad['mebl'], '', '', uyq],
                  'mad', bold=True, white_text=True)
        for mx in g['mexaric']:
            write_row([mx['tarix'], '', mx['emel'], '', mx['mebl'], mx['beyan'], ''],
                      'mex')
        ferq_str = '' if g['uygun'] else f"Fərq: {g['ferq']:+.2f}"
        write_row(['Cəmi:', '', '', mad['mebl'], g['mx_sum'], ferq_str, ''],
                  'cem', bold=True)
        ri += 1  # boş sətir

    widths = [22, 22, 22, 16, 16, 18, 16]
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

    odenilib_cem = madaxil_df[madaxil_df['odenilib']=='Ödənilib']['mebl'].sum()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Mədaxil sətiri",  len(madaxil_df))
    c2.metric("Məxaric sətiri",  len(mexaric_df))
    c3.metric("Ödənilib cəmi",   f"{odenilib_cem:,.2f} AZN")
    c4.metric("Məxaric cəmi",    f"{mexaric_df['mebl'].sum():,.2f} AZN")

    st.divider()
    yalniz_odenilib = st.toggle(
        "Yalnız **Ödənilib** işarəlilər",
        value=True
    )

    with st.spinner("Uyğunlaşdırılır..."):
        groups = uygunlasdir(madaxil_df, mexaric_df, yalniz_odenilib)

    if not groups:
        st.warning("Uyğunlaşdırılacaq məlumat tapılmadı.")
        return

    uygun_say = sum(1 for g in groups if g['uygun'])
    ferq_say  = len(groups) - uygun_say
    r1,r2,r3 = st.columns(3)
    r1.metric("Cəmi qəbz",   len(groups))
    r2.metric("✅ Uyğun",     uygun_say)
    r3.metric("⚠️ Fərq var",  ferq_say)

    st.html(build_html(groups))

    st.divider()
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥 Excel kimi yüklə",
            data=to_excel_bytes(groups),
            file_name="odenis_uygunlasma.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, type="primary"
        )
    with dl2:
        rows_flat = []
        for g in groups:
            mad = g['madaxil']
            rows_flat.append({'Tarix':mad['tarix'],'Ödənişin Təyinatı':mad['teyinat'],
                              'Əməliyyat Növü':'','Ödənilən':mad['mebl'],'Silinən':'','Bəyannamə':''})
            for mx in g['mexaric']:
                rows_flat.append({'Tarix':mx['tarix'],'Ödənişin Təyinatı':'',
                                  'Əməliyyat Növü':mx['emel'],'Ödənilən':'',
                                  'Silinən':mx['mebl'],'Bəyannamə':mx['beyan']})
            rows_flat.append({'Tarix':'Cəmi:','Ödənişin Təyinatı':'','Əməliyyat Növü':'',
                              'Ödənilən':mad['mebl'],'Silinən':g['mx_sum'],'Bəyannamə':''})
        csv = pd.DataFrame(rows_flat).to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📄 CSV kimi yüklə",
            data=csv, file_name="odenis_uygunlasma.csv",
            mime="text/csv", use_container_width=True
        )
