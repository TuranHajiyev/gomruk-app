"""
Excel Redaktoru Bölməsi.
İstənilən Excel faylını yükləyib:
  - Sütun əlavə et / sil / adını dəyiş
  - Məlumatları süzgəcdən keçir (filter)
  - Nəticəni Excel kimi yüklə
"""

import streamlit as st
import pandas as pd
from io import BytesIO


def to_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return buf.getvalue()


def show():
    st.header("📊 Excel Redaktoru")
    st.caption("İstənilən Excel faylını yükləyin — sütunları düzənləyin, süzgəcdən keçirin, yükləyin.")

    uploaded = st.file_uploader(
        "Excel faylı seçin",
        type=["xlsx", "xls"],
        key="excel_editor_upload"
    )

    if not uploaded:
        st.info("Excel faylı yükləyin ki, düzənləmə başlasın.")
        return

    # ── Faylı oxu ─────────────────────────────────────────
    try:
        # Çoxlu vərəq varsa seçim
        xf      = pd.ExcelFile(uploaded)
        sheets  = xf.sheet_names
        sheet   = st.selectbox("Vərəq seçin:", sheets) if len(sheets) > 1 else sheets[0]
        df_orig = pd.read_excel(uploaded, sheet_name=sheet)
    except Exception as e:
        st.error(f"Fayl oxunarkən xəta: {e}")
        return

    st.success(f"✅ {len(df_orig)} sətir, {len(df_orig.columns)} sütun yükləndi.")

    # Session state-da df saxla
    if "editor_df" not in st.session_state or st.session_state.get("editor_file") != uploaded.name:
        st.session_state.editor_df   = df_orig.copy()
        st.session_state.editor_file = uploaded.name

    df = st.session_state.editor_df

    # ── Tab-lar ───────────────────────────────────────────
    t1, t2, t3, t4 = st.tabs([
        "👁️ Önizləmə",
        "🔧 Sütun düzənləmə",
        "🔍 Süzgəc (Filter)",
        "✏️ Cədvəli birbaşa düzənlə"
    ])

    # ── Tab 1: Önizləmə ───────────────────────────────────
    with t1:
        st.dataframe(df, use_container_width=True, height=420)
        st.divider()
        st.download_button(
            "📥 Cari halda Excel yüklə",
            data=to_excel(df),
            file_name=f"redakte_{uploaded.name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary"
        )

    # ── Tab 2: Sütun düzənləmə ────────────────────────────
    with t2:
        st.subheader("Sütun əməliyyatları")

        op = st.radio(
            "Əməliyyat:",
            ["Sütun adını dəyiş", "Sütun sil", "Yeni boş sütun əlavə et", "Sütun sırasını dəyiş"],
            horizontal=True
        )

        if op == "Sütun adını dəyiş":
            col_rename = st.selectbox("Hansı sütunu?", df.columns, key="ren_col")
            new_name   = st.text_input("Yeni ad:", value=col_rename, key="ren_name")
            if st.button("Adı dəyiş", key="btn_rename"):
                st.session_state.editor_df = df.rename(columns={col_rename: new_name})
                st.rerun()

        elif op == "Sütun sil":
            cols_del = st.multiselect("Silinəcək sütunlar:", df.columns, key="del_cols")
            if st.button("Sil", key="btn_del", type="primary"):
                if cols_del:
                    st.session_state.editor_df = df.drop(columns=cols_del)
                    st.rerun()

        elif op == "Yeni boş sütun əlavə et":
            new_col = st.text_input("Yeni sütun adı:", key="new_col_name")
            if st.button("Əlavə et", key="btn_add"):
                if new_col and new_col not in df.columns:
                    st.session_state.editor_df = df.copy()
                    st.session_state.editor_df[new_col] = ""
                    st.rerun()

        elif op == "Sütun sırasını dəyiş":
            st.caption("▲ / ▼ düymələri ilə sıranı dəyişin:")
            col_list = list(df.columns)
            for i, col in enumerate(col_list):
                r1, r2, r3 = st.columns([6, 0.5, 0.5])
                r1.write(f"**{i+1}.** {col}")
                if i > 0 and r2.button("▲", key=f"e_up_{i}"):
                    col_list[i], col_list[i-1] = col_list[i-1], col_list[i]
                    st.session_state.editor_df = df[col_list]
                    st.rerun()
                if i < len(col_list)-1 and r3.button("▼", key=f"e_dn_{i}"):
                    col_list[i], col_list[i+1] = col_list[i+1], col_list[i]
                    st.session_state.editor_df = df[col_list]
                    st.rerun()

        if st.button("🔄 Orijinala qayıt", key="btn_reset"):
            st.session_state.editor_df = df_orig.copy()
            st.rerun()

    # ── Tab 3: Süzgəc ─────────────────────────────────────
    with t3:
        st.subheader("Sütuna görə süzgəc")
        st.caption("Birdən çox sütuna eyni anda süzgəc tətbiq edə bilərsiniz.")

        filter_cols = st.multiselect("Süzgəc tətbiq ediləcək sütunlar:", df.columns, key="f_cols")
        df_filtered = df.copy()

        for fc in filter_cols:
            unique_vals = df[fc].dropna().unique().tolist()
            # Çox unikal dəyər varsa mətn axtarışı, az varsa checkbox
            if len(unique_vals) <= 30:
                selected_vals = st.multiselect(
                    f"**{fc}** — dəyər seçin:",
                    options=unique_vals,
                    default=unique_vals,
                    key=f"fv_{fc}"
                )
                df_filtered = df_filtered[df_filtered[fc].isin(selected_vals)]
            else:
                search = st.text_input(f"**{fc}** — axtarış:", key=f"fs_{fc}")
                if search:
                    df_filtered = df_filtered[
                        df_filtered[fc].astype(str).str.contains(search, case=False, na=False)
                    ]

        st.info(f"Süzgəcdən keçən sətir: **{len(df_filtered)}** / {len(df)}")
        st.dataframe(df_filtered, use_container_width=True, height=380)

        st.divider()
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "📥 Süzülmüş Excel yüklə",
                data=to_excel(df_filtered),
                file_name=f"suzulmus_{uploaded.name}",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
        with dl2:
            st.download_button(
                "📥 CSV kimi yüklə",
                data=df_filtered.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"suzulmus_{uploaded.name.replace('.xlsx','.csv')}",
                mime="text/csv",
                use_container_width=True
            )

    # ── Tab 4: Birbaşa düzənlə ────────────────────────────
    with t4:
        st.caption("Hücrələri birbaşa dəyişdirin. Dəyişiklikdən sonra 'Saxla' düyməsinə basın.")
        edited = st.data_editor(
            df,
            use_container_width=True,
            height=420,
            num_rows="dynamic",
            key="data_editor_widget"
        )
        if st.button("💾 Dəyişiklikləri saxla", type="primary"):
            st.session_state.editor_df = edited
            st.success("✅ Saxlanıldı!")
            st.rerun()

        st.divider()
        st.download_button(
            "📥 Düzənlənmiş Excel yüklə",
            data=to_excel(edited),
            file_name=f"duzenli_{uploaded.name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
