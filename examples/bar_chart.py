"""
Bar chart: one cube per data point, height and spacing driven by scales.
Run: python examples/bar_chart.py
See bar_chart_blender.py for this same script converted to run against a
real Blender scene instead of the mock.

The attribute-setting below is one continuous chain off .join() --
.attr(key, fn) accessors receive (el, d, i), the bound datum included,
matching real d3's own `.attr("x", d => ...)` idiom. That's
Selection.datum (see selection.py) -- Join.join() tracks each entered/
updated element's own datum alongside it, not just its index, so you
don't need to close over `data` and re-index by `i` the way you would
have before.
"""

from d3blender import select, scale_linear, scale_band, scale_ordinal
from d3blender.mock import new_scene, spawn

adapter, chart = new_scene('Chart')

data = [
    {'label': 'Jan', 'revenue': 12},
    {'label': 'Feb', 'revenue': 18},
    {'label': 'Mar', 'revenue': 9},
    {'label': 'Apr', 'revenue': 24},
]

x = scale_band([d['label'] for d in data], range_=(0, 8), padding=0.2)
height = scale_linear(domain=(0, 24), range_=(0.2, 4.0))
color = scale_ordinal([d['label'] for d in data],
                       range_=['#E8B75D', '#5B8DEF', '#5DE8A6', '#E85D9E'])

bars = (
    select(adapter, '#Chart mesh')
    .data(data, key=lambda i, d: d['label'])
    # spawn() stands in for bpy.ops.mesh.primitive_cube_add() + rename,
    # or databpy's db.create_object('CUBE', name=name)
    .join(enter=lambda d: spawn(adapter, chart, f"bar_{d['label']}"))
    .attr('location', lambda el, d, i: (x(d['label']), 0, height(d['revenue']) / 2))
    .attr('scale', lambda el, d, i: (x.bandwidth() / 2, 0.5, height(d['revenue']) / 2))
    .attr('revenue', lambda el, d, i: d['revenue'])
    .attr('fill', lambda el, d, i: color(d['label']))
)

if __name__ == '__main__':
    bars.each(lambda el, i: print(f"{el.name}: loc={el.location} scale={el.scale} fill={el['fill']}"))
