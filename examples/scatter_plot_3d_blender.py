"""
scatter_plot_3d.py, but wired to a real Blender scene instead of the mock.
This is the pattern for turning any of the mock-based examples into
something you actually run inside Blender: drop the adapter (inside
Blender, select_all() gets a live one itself) and swap mock.spawn() for
a shape name -- join('uv_sphere', radius=0.3) calls Blender's
primitive_uv_sphere_add and links each new sphere into the selection's
collection. The mock has no bpy.ops, so it keeps its explicit spawn().

With a shape name there's no enter/update callback to put per-element
setup in; the join result's .entered and .updated sub-selections do
that job instead (new points get placed, existing ones animate).

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

import d3blender as d3
from d3blender import scale_linear, scale_ordinal

chart = d3.collection('Scatter')  # d3.create('svg'), Blender-flavored

sx = scale_linear(domain=(0, 5), range_=(-5, 5))
sy = scale_linear(domain=(0, 5), range_=(-5, 5))
sz = scale_linear(domain=(0, 5), range_=(-5, 5))
color = scale_ordinal(['a', 'b'], range_=['#E8B75D', '#5B8DEF'])
FPS = 24



def pos(el, d, i):
    return (sx(d['x']), sy(d['y']), sz(d['z']))


def join_points(data):
    # The default exit removes points whose id is no longer in the data.
    return (d3.select_all(chart)
            .data(data, key='id')
            .join('uv_sphere', radius=0.3)
            .attr('fill', lambda el, d, i: color(d['group'])))


def place_new(points):
    points.entered.attr('name', lambda el, d, i: f"pt_{d['id']}").attr('location', pos)
    return points


points_v1 = [
    {'id': 0, 'x': 1.2, 'y': 3.4, 'z': 0.5, 'group': 'a'},
    {'id': 1, 'x': 4.5, 'y': 1.1, 'z': 2.2, 'group': 'b'},
    {'id': 2, 'x': 2.8, 'y': 4.9, 'z': 1.7, 'group': 'a'},
]
place_new(join_points(points_v1))

# The change: point 0 stays put, point 1 moves, point 2 exits, point 3 enters.
points_v2 = [
    {'id': 0, 'x': 1.2, 'y': 3.4, 'z': 0.5, 'group': 'a'},
    {'id': 1, 'x': 0.6, 'y': 4.8, 'z': 3.9, 'group': 'b'},
    {'id': 3, 'x': 3.3, 'y': 2.2, 'z': 4.4, 'group': 'b'},
]
result = place_new(join_points(points_v2))
(result.updated
 .keyframe(1, location=lambda el: tuple(el.location))  # hold current pose
 .keyframe(FPS, location=pos))                         # animate to new position

print('points remaining:', sorted(el.name for el in result))
result.each(lambda el, i: print(
    f"{el.name}: loc={tuple(round(v, 2) for v in el.location)} fill={el['fill']}"))
