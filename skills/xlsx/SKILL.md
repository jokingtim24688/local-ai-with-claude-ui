---
name: xlsx
description: Create/read/edit Excel spreadsheets, formulas, charts.
---

# xlsx

`pip install openpyxl` (xlsx) · `pandas` for data-heavy work.
```python
import openpyxl
wb = openpyxl.Workbook(); ws = wb.active
ws["A1"]="n"; ws["B1"]="sq"
for i in range(2,7): ws[f"A{i}"]=i; ws[f"B{i}"]=f"=A{i}^2"
wb.save("out.xlsx")
```
Read: `openpyxl.load_workbook("f.xlsx", data_only=True)`. Charts: `openpyxl.chart`.
CSV/TSV clean-up: pandas `read_csv`/`to_excel`.
