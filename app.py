"""
Gömrük Komitəsi Alətlər Dəsti  |  Streamlit web proqramı
"""

import streamlit as st
import pandas as pd
from gomruk_reader import read_gomruk_file, get_clean_columns
from converter import fill_template, to_excel_bytes
from mal_parser import parse_mal
import ocr_page
import excel_editor_page
import odenis_page


def _auto_match(template_col, source_cols):
    t = template_col.lower()
    kw = {
        'gb':'GB Sorğu Nömrəsi','nömrə':'GB Sorğu Nömrəsi',
        'tarix':'Bəyannamə Tarixi','date':'Bəyannamə Tarixi',
        'tərəf':'Xarici Tərəfdaş','partner':'Xarici Tərəfdaş',
        'mal':'Malın Adı','kod':'Malın Kodu (HS)','hs':'Malın Kodu (HS)',
        'netto':'Netto Çəki (kq)','çəki':'Netto Çəki (kq)',
        'dəyər':'Statistik Dəyər (USD)','value':'Statistik Dəyər (USD)',
        'edv':'ƏDV (AZN)','vat':'ƏDV (AZN)',
        'rüsum':'İdxal Rüsumu (AZN)','duty':'İdxal Rüsumu (AZN)',
        'gömrük':'Gömrük Yığımı (AZN)','aksiz':'Aksiz (AZN)',
    }
    for k, v in kw.items():
        if k in t and v in source_cols:
            return v
    return "(boş bur)"


def _parse_miqdari(val):
    """'14344.0 kq' → ('14344.0', 'kq') kimi ayırır."""
    import re
    text = str(val).strip()
    m = re.match(r'^([\d.,]+)\s*(ədəd|əd|kq|m2|m3|yer|cüt|ton)?', text, re.IGNORECASE)
    if m:
        miqdar = m.group(1).replace(',', '.')
        vahid  = m.group(2) or ''
        if vahid.lower() in ('əd', 'ədəd'):
            vahid = 'ədəd'
        return miqdar, vahid.lower()
    return '', ''


def build_parsed_df(df):
    cols      = list(df.columns)
    mal_idx   = cols.index('Malın Adı') if 'Malın Adı' in cols else -1
    pre_cols  = cols[:mal_idx] if mal_idx >= 0 else cols
    post_cols = cols[mal_idx+1:] if mal_idx >= 0 else []
    miqdari_col = 'Malın Miqdarı' if 'Malın Miqdarı' in cols else None
    out_cols  = pre_cols + ['Malın Adı', 'Ölçü Vahidi', 'Miqdar'] + post_cols
    rows = []

    for _, row in df.iterrows():
        mal_raw = str(row.get('Malın Adı', '')).replace('\n', ' ').strip()
        for p in parse_mal(mal_raw):
            new_row = {c: row[c] for c in pre_cols + post_cols}
            new_row['Malın Adı'] = p['Malın Adı']
            if (not p['Ölçü Vahidi'] or not p['Miqdar']) and miqdari_col:
                fb_miqdar, fb_vahid    = _parse_miqdari(row[miqdari_col])
                new_row['Ölçü Vahidi'] = p['Ölçü Vahidi'] or fb_vahid
                new_row['Miqdar']      = p['Miqdar']      or fb_miqdar
            else:
                new_row['Ölçü Vahidi'] = p['Ölçü Vahidi']
                new_row['Miqdar']      = p['Miqdar']
            rows.append(new_row)

    result = pd.DataFrame(rows, columns=out_cols)
    result['Miqdar'] = pd.to_numeric(result['Miqdar'], errors='coerce')
    return result


# ── Konfiqurasiya ──────────────────────────────────────────
st.set_page_config(page_title="Gömrük Alətlər", page_icon="🛃", layout="wide")

st.markdown("""
<style>
[data-testid="stDataFrameResizable"] { overflow-x: auto !important; }
.dvn-scroller { overflow-x: scroll !important; scrollbar-width: auto !important; }
.dvn-scroller::-webkit-scrollbar { height: 10px; display: block !important; }
.dvn-scroller::-webkit-scrollbar-thumb { background: #555; border-radius: 5px; }
.dvn-scroller::-webkit-scrollbar-track { background: #222; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar naviqasiya ─────────────────────────────────────
with st.sidebar:
    st.title("🛃 Gömrük Alətlər")
    st.divider()
    page = st.radio(
        "Bölmə seçin:",
        ["🛃 Gömrük Hesabatı", "💳 Ödəniş Uyğunlaşdırma", "📄 OCR (Şəkil → Mətn)", "📊 Excel Redaktoru"],
        label_visibility="collapsed"
    )
    st.divider()
    st.caption("v2.0 | Turan Hajiyev")

# ── Səhifə yönləndirmə ────────────────────────────────────
if page == "💳 Ödəniş Uyğunlaşdırma":
    odenis_page.show()
    st.stop()

if page == "📄 OCR (Şəkil → Mətn)":
    ocr_page.show()
    st.stop()

if page == "📊 Excel Redaktoru":
    excel_editor_page.show()
    st.stop()

# ── Gömrük Hesabatı bölməsi (əsas) ───────────────────────
st.title("🛃 Gömrük Hesabatı → Şablon Çeviricisi")
st.caption("Dövlət Gömrük Komitəsinin hesabat faylını istənilən şablona çevirin.")

# ── 1. Fayllar ────────────────────────────────────────────
st.divider()
c1, c2 = st.columns(2)
with c1:
    st.subheader("📂 Gömrük hesabatı")
    source_file = st.file_uploader("Hesabat faylını yükləyin", type=["xlsx","xls"])
with c2:
    st.subheader("📋 Hədəf şablon (isteğe bağlı)")
    template_file = st.file_uploader("Şablon faylını yükləyin", type=["xlsx"])

if not source_file:
    st.info("Əvvəlcə Gömrük hesabat faylını yükləyin.")
    st.stop()

# ── 2. Oxuma ──────────────────────────────────────────────
with st.spinner("Fayl oxunur..."):
    try:
        df, meta = read_gomruk_file(source_file)
    except Exception as e:
        st.error(f"Fayl oxunarkən xəta: {e}")
        st.stop()

st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("VÖEN", meta.get('voen','—'))
m2.metric("Hesabat dövrü", meta.get('dovr','—'))
m3.metric("Cəmi sətir", len(df))
m4.metric("Bəyannamə sayı", df['GB Sorğu Nömrəsi'].nunique() if 'GB Sorğu Nömrəsi' in df.columns else '—')
if meta.get('shirket'):
    st.info(f"🏢 **{meta['shirket']}**")

# ── 3. Sütun seçimi və sıralama ──────────────────────────
st.divider()
st.subheader("1️⃣ Hansı sütunları istifadə etmək istəyirsiniz?")
all_cols = get_clean_columns(df)
default_cols = [c for c in all_cols if c in [
    'GB Sorğu Nömrəsi','Bəyannamə Tarixi','Malın Adı',
    'Malın Kodu (HS)','Netto Çəki (kq)','Statistik Dəyər (USD)',
    'ƏDV (AZN)','İdxal Rüsumu (AZN)'
]]

# Session state-də sütun sırasını saxla
if 'col_order' not in st.session_state:
    st.session_state.col_order = default_cols

# Sütun seçimi
chosen = st.multiselect("Sütunları seçin:", options=all_cols, default=st.session_state.col_order)
if not chosen:
    st.warning("Ən azı bir sütun seçin.")
    st.stop()

# Köhnə sıranı qoru, yeni əlavə olunanları sona əlavə et
prev_order = [c for c in st.session_state.col_order if c in chosen]
new_added  = [c for c in chosen if c not in prev_order]
st.session_state.col_order = prev_order + new_added
selected_cols = st.session_state.col_order

# Sütun sırasını əl ilə düzənlə
st.caption("📌 Sütun sırasını dəyişmək üçün yuxarı/aşağı düymələrindən istifadə edin:")
reorder_cols = list(selected_cols)
for i, col in enumerate(reorder_cols):
    c1, c2, c3 = st.columns([6, 0.5, 0.5])
    c1.write(f"**{i+1}.** {col}")
    if i > 0 and c2.button("▲", key=f"up_{i}"):
        reorder_cols[i], reorder_cols[i-1] = reorder_cols[i-1], reorder_cols[i]
        st.session_state.col_order = reorder_cols
        st.rerun()
    if i < len(reorder_cols)-1 and c3.button("▼", key=f"dn_{i}"):
        reorder_cols[i], reorder_cols[i+1] = reorder_cols[i+1], reorder_cols[i]
        st.session_state.col_order = reorder_cols
        st.rerun()

selected_cols = st.session_state.col_order
df_selected = df.reindex(columns=selected_cols).copy()

# ── 4. İki tab ────────────────────────────────────────────
st.divider()
tab1, tab2 = st.tabs(["📋 Adi görünüş", "🔪 Malın adını ayır  (ad · ölçü · miqdar)"])

# ── Tab 1: Adi ────────────────────────────────────────────
with tab1:
    st.dataframe(df_selected.head(30), use_container_width=True)
    st.divider()
    plain_bytes = to_excel_bytes(df_selected)
    st.download_button(
        "📥 Excel kimi yüklə (orijinal)",
        data=plain_bytes,
        file_name=f"gomruk_{meta.get('voen','')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# ── Tab 2: Ayır ───────────────────────────────────────────
with tab2:
    if 'Malın Adı' not in selected_cols:
        st.warning("Yuxarıdakı sütun seçimindən **Malın Adı** sütununu əlavə edin.")
        st.stop()

    st.info(
        "**Malın adı** sütunundakı mətn parçalanır:\n\n"
        "- Malın adı təmiz qalır\n"
        "- Ədəd/miqdar → **Miqdar** sütunu\n"
        "- Ölçü vahidi (ədəd, kq, m2...) → **Ölçü Vahidi** sütunu\n"
        "- Şirkət adları (YIWU, GLOBAL DENPA...) **silinir**"
    )

    with st.spinner("Parçalanır..."):
        df_parsed = build_parsed_df(df_selected)

    s1, s2, s3 = st.columns(3)
    s1.metric("Cəmi sətir", len(df_parsed))
    s2.metric("Unikal mal adı", df_parsed['Malın Adı'].nunique())
    s3.metric("Boş ölçü vahidi", (df_parsed['Ölçü Vahidi'] == '').sum())

    st.dataframe(df_parsed, use_container_width=True, height=420)

    st.divider()
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥 Excel kimi yüklə (ayırılmış)",
            data=to_excel_bytes(df_parsed),
            file_name=f"mallar_ayrilmis_{meta.get('voen','')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary"
        )
    with dl2:
        st.download_button(
            "📥 CSV kimi yüklə",
            data=df_parsed.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"mallar_ayrilmis_{meta.get('voen','')}.csv",
            mime="text/csv",
            use_container_width=True
        )

# ── 5. Şablon xəritəsi ────────────────────────────────────
if template_file:
    template_bytes = template_file.getvalue()
    try:
        template_cols = list(pd.read_excel(template_file).columns)
    except Exception as e:
        st.error(f"Şablon oxunarkən xəta: {e}")
        st.stop()

    st.divider()
    st.subheader("2️⃣ Şablon sütunlarını uyğunlaşdırın")

    use_parsed = st.toggle(
        "Ayırılmış məlumatı şablona köçür (Malın adı / Ölçü vahidi / Miqdar)",
        value=True
    )
    df_tmpl = df_parsed if (use_parsed and 'Malın Adı' in selected_cols) else df_selected
    avail   = list(df_tmpl.columns)
    choices = ["(boş bur)"] + avail
    mapping = {}

    for row in [template_cols[i:i+3] for i in range(0, len(template_cols), 3)]:
        ucols = st.columns(3)
        for uc, tcol in zip(ucols, row):
            with uc:
                auto = _auto_match(tcol, avail)
                mapping[tcol] = st.selectbox(
                    f"**{tcol}**", choices,
                    index=choices.index(auto) if auto in choices else 0,
                    key=f"map_{tcol}"
                )

    st.divider()
    if st.button("📋 Şablona köçür və yüklə", type="primary", use_container_width=True):
        active = {k: v for k, v in mapping.items() if v != "(boş bur)"}
        if not active:
            st.warning("Ən azı bir sütun uyğunlaşdırın.")
        else:
            try:
                with st.spinner("Şablon doldurulur..."):
                    result = fill_template(df_tmpl, template_bytes, active)
                st.success(f"✅ {len(df_tmpl)} sətir şablona yazıldı.")
                st.download_button(
                    "⬇️ Şablonu yüklə",
                    data=result,
                    file_name=f"sablon_{meta.get('voen','')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Xəta: {e}")
