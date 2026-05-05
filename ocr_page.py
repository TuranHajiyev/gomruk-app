"""
OCR Bölməsi — PDF / JPG / PNG fayllarından mətn çıxarır.
Tesseract OCR istifadə edir (pulsuz).
Nəticə: Word (.docx) + TXT (.txt)
"""

import streamlit as st
import pytesseract
from PIL import Image
from io import BytesIO
from pathlib import Path


def pdf_to_images(pdf_bytes: bytes) -> list:
    try:
        from pdf2image import convert_from_bytes
        return convert_from_bytes(pdf_bytes, dpi=200)
    except Exception as e:
        st.error(f"PDF açılarkən xəta: {e}")
        return []


def ocr_image(img, lang_code: str) -> str:
    try:
        text = pytesseract.image_to_string(img, lang=lang_code)
        return text.strip()
    except Exception as e:
        return f"[Xəta: {e}]"


def make_docx(text: str, title: str) -> bytes:
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    doc.add_heading(title, level=1)
    for para in text.split('\n'):
        p = doc.add_paragraph(para)
        p.style.font.size = Pt(11)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def show():
    st.header("📄 OCR — Şəkil / PDF → Mətn")
    st.caption("PDF, JPG, PNG fayllarını yükləyin — mətn avtomatik çıxarılır.")

    # Dil seçimi
    lang = st.selectbox(
        "Sənədin dili:",
        ["Azərbaycan + Rus", "Azərbaycan", "Rus", "İngilis", "Azərbaycan + Rus + İngilis"],
        index=0
    )
    lang_map = {
        "Azərbaycan + Rus":              "aze+rus",
        "Azərbaycan":                    "aze",
        "Rus":                           "rus",
        "İngilis":                       "eng",
        "Azərbaycan + Rus + İngilis":    "aze+rus+eng",
    }
    lang_code = lang_map[lang]

    # Fayl yükləmə
    uploaded = st.file_uploader(
        "Fayl seçin (PDF, JPG, PNG — çoxlu fayl ola bilər)",
        type=["pdf", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="ocr_uploader"
    )

    if not uploaded:
        st.info("Fayl yükləyin ki, OCR başlasın.")
        return

    if st.button("🔍 Mətni çıxar", type="primary", use_container_width=True):
        all_texts = []
        progress  = st.progress(0, text="Hazırlanır...")
        total     = len(uploaded)

        for fi, uf in enumerate(uploaded):
            file_bytes = uf.read()
            fname      = uf.name
            ext        = Path(fname).suffix.lower()

            st.markdown(f"**📄 {fname}**")

            if ext == ".pdf":
                pages      = pdf_to_images(file_bytes)
                page_texts = []
                for pi, page_img in enumerate(pages):
                    progress.progress(
                        (fi / total) + (pi / max(len(pages), 1) / total),
                        text=f"{fname} — səhifə {pi+1}/{len(pages)}"
                    )
                    page_texts.append(ocr_image(page_img, lang_code))
                file_text = "\n\n--- Səhifə sonu ---\n\n".join(page_texts)
            else:
                progress.progress(fi / total, text=f"{fname} oxunur...")
                img       = Image.open(BytesIO(file_bytes))
                file_text = ocr_image(img, lang_code)

            st.text_area(
                f"Çıxarılan mətn — {fname}",
                value=file_text,
                height=220,
                key=f"txt_{fi}"
            )
            all_texts.append(f"=== {fname} ===\n\n{file_text}")

        progress.progress(1.0, text="✅ Tamamlandı!")
        combined = "\n\n".join(all_texts)

        st.divider()
        st.subheader("⬇️ Nəticəni yüklə")
        dl1, dl2 = st.columns(2)

        with dl1:
            st.download_button(
                "📝 Word (.docx) kimi yüklə",
                data=make_docx(combined, "OCR Nəticəsi"),
                file_name="ocr_netice.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                type="primary"
            )
        with dl2:
            st.download_button(
                "📄 TXT kimi yüklə",
                data=combined.encode("utf-8"),
                file_name="ocr_netice.txt",
                mime="text/plain",
                use_container_width=True
            )
