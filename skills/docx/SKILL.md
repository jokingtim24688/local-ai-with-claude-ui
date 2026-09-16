---
name: docx
description: Create/read/edit Word .docx files.
---

# docx

`pip install python-docx`
```python
from docx import Document
d = Document()
d.add_heading("Title", 0); d.add_paragraph("body")
d.add_table(rows=2, cols=3)
d.save("out.docx")
```
Read: `Document("in.docx").paragraphs[i].text`. Images: `add_picture`. For
letterheads/TOC/page numbers, edit the underlying XML or start from a template.
