"""
bar_chart.py, but wired to a real Blender scene instead of the mock.
Same conversion recipe as scatter_plot_3d.py -> scatter_plot_3d_blender.py
(see that pair too, for the enter/update/exit case this one doesn't
need): drop the adapter (inside Blender, select_all() gets a live one
itself) and swap mock.spawn() for join('cube') -- d3's own
`selection.join("rect")` shorthand, which calls Blender's
primitive_cube_add and links each new cube into the selection's
collection. The mock has no bpy.ops, so it keeps its explicit spawn().
Everything else -- scales, keys, the .attr() chain -- is unchanged.

d3blender must already be importable from Blender's own Python -- see the
README's "Using it inside Blender" section.

Run it one of two ways:
  - Paste into Blender's Scripting workspace and click "Run Script".
  - From a terminal: blender --python examples/bar_chart_blender.py
    (add --background to run headless, no window).

This has been run against real bpy (PyPI's headless module -- see
tests/blender/), not yet against the full Blender application; if
something here doesn't match your Blender version, that's expected --
see CLAUDE.md's "Testing status" section.

The attribute-setting below is one continuous chain off .join() --
.attr(key, fn) accessors receive (el, d, i), the bound datum included,
matching real d3's own `.attr("x", d => ...)` idiom (see
Selection.datum in selection.py).
"""

import d3blender as d3
from d3blender import scale_linear, scale_band, scale_ordinal

chart = d3.collection('Bar Chart')

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
    d3.select_all(chart)
    .data(data, key='label')
    .join('cube')  # size 2, so scale is half the bar's extent
    .attr('name', lambda el, d, i: f"bar_{d['label']}")
    .attr('location', lambda el, d, i: (x(d['label']), 0, height(d['revenue']) / 2))
    .attr('scale', lambda el, d, i: (x.bandwidth() / 2, 0.5, height(d['revenue']) / 2))
    .attr('revenue', lambda el, d, i: d['revenue'])
    .attr('fill', lambda el, d, i: color(d['label']))
)

bars.each(lambda el, i: print(f"{el.name}: loc={el.location} scale={el.scale} fill={el['fill']}"))
