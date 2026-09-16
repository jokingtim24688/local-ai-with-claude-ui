---
name: pdf
description: Read, extract, merge, split, fill, OCR PDFs.
---

# pdf

- Text/extract: `pypdf` (`PdfReader("f.pdf").pages[i].extract_text()`) or `pdfplumber` (tables).
- Merge/split/rotate: `pypdf` `PdfWriter`.
- Create: `reportlab` (`canvas.Canvas`) or render HTML→PDF with `weasyprint`.
- Forms: `pypdf` `update_page_form_field_values`.
- Scanned → searchable: `ocrmypdf in.pdf out.pdf` (Tesseract).
