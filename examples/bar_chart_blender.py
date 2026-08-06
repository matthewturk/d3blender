"""
bar_chart.py, but wired to a real Blender scene instead of the mock.
Same conversion recipe as scatter_plot_3d.py -> scatter_plot_3d_blender.py
(see that pair too, for the enter/update/exit case this one doesn't
need): swap the adapter (d3blender.mock -> get_adapter()) and swap
object creation (mock.spawn() -> real bpy.ops/bpy.data calls), since
object creation is Blender-specific and the library deliberately doesn't
wrap it (see CLAUDE.md). Everything else -- scales, the selector, the
join itself -- is unchanged: adapter-agnostic code never needs to know
which adapter it's running against.

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
"""

import bpy

from d3blender import select, scale_linear, scale_band, scale_ordinal
from d3blender.blender_adapter import get_adapter

adapter = get_adapter()
chart = adapter.get_or_create_collection('Chart')  # unchanged from the mock version

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


def spawn_cube(name):
    # The Blender-specific stand-in for mock.spawn() -- real object
    # creation, which d3blender deliberately doesn't wrap (see CLAUDE.md
    # -- databpy's db.create_object('CUBE', name=name) is another option
    # here if you're already depending on databpy).
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = name
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    chart.objects.link(obj)
    return obj


bars = (select(adapter, '#Chart mesh')
        .data(data, key=lambda i, d: d['label'])
        .join(enter=lambda d: spawn_cube(f"bar_{d['label']}")))

for el, d in zip(bars.elements, data):
    h = height(d['revenue'])
    el.location = (x(d['label']), 0, h / 2)          # sits on the ground, grows up
    el.scale = (x.bandwidth() / 2, 0.5, h / 2)        # cube default is 2x2x2, halve for unit scale
    el['revenue'] = d['revenue']
    el['fill'] = color(d['label'])

bars.each(lambda el, i: print(f"{el.name}: loc={el.location} scale={el.scale} fill={el['fill']}"))
