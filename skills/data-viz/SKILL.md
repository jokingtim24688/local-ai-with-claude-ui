---
name: data-viz
description: Design clear charts/dashboards with an accessible, consistent palette.
---

# data-viz

Pick the form from the question: trend→line, compare→bar, part-of-whole→stacked/treemap
(not pie for many slices), correlation→scatter, distribution→histogram/box.
Color: categorical = distinct hues equal value; sequential = one hue light→dark;
diverging = two hues around a neutral mid. Keep it consistent across a dashboard.
Always: labeled axes with units, direct labels over legends when few series,
tooltips, and check contrast in light + dark. Libs: Recharts/D3 (web), matplotlib/
plotly (python).
