---
name: pptx
description: Create/read/edit PowerPoint .pptx decks.
---

# pptx

`pip install python-pptx`
```python
from pptx import Presentation
from pptx.util import Inches
p = Presentation()
s = p.slides.add_slide(p.slide_layouts[1])
s.shapes.title.text = "Hello"
s.placeholders[1].text = "bullet"
p.save("deck.pptx")
```
Add images `add_picture`, tables `add_table`, charts `add_chart`. Read text by
iterating `slide.shapes` where `shape.has_text_frame`.
