"""
Çevirmə məntiqi: mənbə DataFrame-dən şablona məlumat yazır.
"""

import pandas as pd
from copy import copy as copy_obj
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Border, Alignment
from io import BytesIO


def fill_template(source_df: pd.DataFrame,
                  template_bytes: bytes,
                  mapping: dict,
                  header_row: int = 1) -> bytes:
    """
    Şablonu açır, başlıq sırasından sonra məlumatları yazır.
    Şablonun formatı (font, rəng, kənar) qorunur.
    """
    wb = load_workbook(BytesIO(template_bytes))
    ws = wb.active

    # Şablondakı başlıq sütunlarını tap
    template_headers = {}
    for cell in ws[header_row]:
        if cell.value is not None:
            clean = str(cell.value).strip()
            template_headers[clean] = cell.column

    # Başlıqdan sonrakı köhnə sətirləri sil
    last_row = ws.max_row
    if last_row > header_row:
        ws.delete_rows(header_row + 1, last_row - header_row)

    # Hər şablon sütunu üçün stil nümunəsi götür
    style_refs = {}
    for col_name, col_idx in template_headers.items():
        style_refs[col_name] = ws.cell(row=header_row, column=col_idx)

    # Məlumatları yaz
    for row_idx, (_, src_row) in enumerate(source_df.iterrows(), start=header_row + 1):
        for tmpl_col, src_col in mapping.items():
            col_idx = template_headers.get(tmpl_col)
            if col_idx is None:
                continue
            cell = ws.cell(row=row_idx, column=col_idx)

            # Dəyər
            if src_col == "(boş bur)":
                cell.value = ""
            else:
                val = src_row.get(src_col, "")
                cell.value = None if pd.isna(val) else val

            # Stil kopyala
            ref = style_refs.get(tmpl_col)
            if ref:
                if ref.font:      cell.font      = copy_obj(ref.font)
                if ref.fill:      cell.fill      = copy_obj(ref.fill)
                if ref.border:    cell.border    = copy_obj(ref.border)
                if ref.alignment: cell.alignment = copy_obj(ref.alignment)
                if ref.number_format: cell.number_format = ref.number_format

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """DataFrame-i sadə Excel faylına çevirir (şablonsuz)."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buf.getvalue()
