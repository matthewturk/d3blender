"""
3D scatter plot: three independent linear scales (x, y, z) placing
spheres instead of the flat, z=0 cubes in scatter_plot.py -- then a
"change", d3's general update pattern in three dimensions: rerun with a
new data array and existing points animate to their new position, a
dropped point exits, and a new point enters.
Run: python examples/scatter_plot_3d.py
"""

from d3blender import select, scale_linear, scale_ordinal
from d3blender.mock import new_scene, spawn

adapter, chart = new_scene('Chart')

sx = scale_linear(domain=(0, 5), range_=(-5, 5))
sy = scale_linear(domain=(0, 5), range_=(-5, 5))
sz = scale_linear(domain=(0, 5), range_=(-5, 5))
color = scale_ordinal(['a', 'b'], range_=['#E8B75D', '#5B8DEF'])
FPS = 24


def points():
    return select(adapter, '#Chart mesh').filter(lambda el: el.name.startswith('pt_'))


def enter_point(d):
    # stand-in for bpy.ops.mesh.primitive_uv_sphere_add() + rename
    el = spawn(adapter, chart, f"pt_{d['id']}")
    el.location = (sx(d['x']), sy(d['y']), sz(d['z']))
    el.scale = (0.3, 0.3, 0.3)
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

if __name__ == '__main__':
    print('points remaining:', sorted(el.name for el in result))
    result.each(lambda el, i: print(
        f"{el.name}: loc={tuple(round(v, 2) for v in el.location)} fill={el['fill']}"))
