"""
scatter_plot_3d.py, but wired to a real Blender scene instead of the mock.
This is the pattern for turning any of the mock-based examples into
something you actually run inside Blender: swap the adapter
(d3blender.mock -> d3blender.blender_adapter.get_adapter()) and swap
object creation (mock.spawn() -> real bpy.ops/bpy.data calls), since
object creation is Blender-specific and the library deliberately doesn't
wrap it (see CLAUDE.md). Getting the chart-root collection itself *is*
generalized, though -- get_or_create_collection() works the same way on
both adapters.

d3blender must already be importable from Blender's own Python -- see the
README's "Using it inside Blender" section.

Run it one of two ways:
  - Paste into Blender's Scripting workspace and click "Run Script".
  - From a terminal: blender --python examples/scatter_plot_3d_blender.py
    (add --background to run headless, no window).

NOTE: blender_adapter.py is written against documented, stable bpy API
but has not been exercised against a live Blender install by the
maintainers -- if something here doesn't match your Blender version,
that's expected; see CLAUDE.md's "Testing status" section.
"""

import bpy

from d3blender import select, scale_linear, scale_ordinal
from d3blender.blender_adapter import get_adapter

adapter = get_adapter()
chart = adapter.get_or_create_collection('Chart')  # d3.create('svg'), Blender-flavored

sx = scale_linear(domain=(0, 5), range_=(-5, 5))
sy = scale_linear(domain=(0, 5), range_=(-5, 5))
sz = scale_linear(domain=(0, 5), range_=(-5, 5))
color = scale_ordinal(['a', 'b'], range_=['#E8B75D', '#5B8DEF'])
FPS = 24


def spawn_sphere(name):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3)
    obj = bpy.context.active_object
    obj.name = name
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    chart.objects.link(obj)
    return obj


def points():
    return select(adapter, '#Chart mesh').filter(lambda el: el.name.startswith('pt_'))


def enter_point(d):
    el = spawn_sphere(f"pt_{d['id']}")
    el.location = (sx(d['x']), sy(d['y']), sz(d['z']))
    el['fill'] = color(d['group'])
    return el


def update_point(el, d):
    sel = select(adapter, el)  # re-wrap the known element -- no CSS round trip
    sel.keyframe(1, location=el.location)                                    # hold current pose
    sel.keyframe(FPS, location=(sx(d['x']), sy(d['y']), sz(d['z'])))          # animate to new position
    el['fill'] = color(d['group'])


def exit_point(el):
    adapter.remove(el)


points_v1 = [
    {'id': 0, 'x': 1.2, 'y': 3.4, 'z': 0.5, 'group': 'a'},
    {'id': 1, 'x': 4.5, 'y': 1.1, 'z': 2.2, 'group': 'b'},
    {'id': 2, 'x': 2.8, 'y': 4.9, 'z': 1.7, 'group': 'a'},
]
points().data(points_v1, key=lambda i, d: d['id']).join(enter=enter_point)

# The change: point 0 stays put, point 1 moves, point 2 exits, point 3 enters.
points_v2 = [
    {'id': 0, 'x': 1.2, 'y': 3.4, 'z': 0.5, 'group': 'a'},
    {'id': 1, 'x': 0.6, 'y': 4.8, 'z': 3.9, 'group': 'b'},
    {'id': 3, 'x': 3.3, 'y': 2.2, 'z': 4.4, 'group': 'b'},
]
result = points().data(points_v2, key=lambda i, d: d['id']).join(
    enter=enter_point, update=update_point, exit=exit_point)

print('points remaining:', sorted(el.name for el in result))
result.each(lambda el, i: print(
    f"{el.name}: loc={tuple(round(v, 2) for v in el.location)} fill={el['fill']}"))
