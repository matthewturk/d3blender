"""
nested_point_deformation.py, but wired to a real Blender scene instead
of the mock. Same conversion recipe as the other *_blender.py examples
(see bar_chart_blender.py): swap the adapter (d3blender.mock ->
get_adapter()) and swap object creation (mock.spawn_points() -> real
bpy.data.meshes.new()+from_pydata()); everything else -- the two levels
of position, the relative-vs-strictly-local contrast, the nested
closures -- is unchanged, because none of it is adapter-specific.

Unlike the mock version, this one drives the deformation with
live_point_data() instead of an explicit per-frame bake loop -- so
after running this script, **pressing Play or scrubbing the timeline in
Blender's own UI is what actually animates the spheres**, live, exactly
the way scatter_plot_3d_blender.py's real F-curve keyframes do, even
though the mechanism underneath is different (recompute-on-frame-change
here, not baked keyframe data -- see points.point_data's docstring and
CLAUDE.md for why point data can't be keyframed the way position on an
object can). Running the script itself just registers the live binding
and applies frame 1 -- nothing "plays" until you interact with the
timeline.

Run: blender --python examples/nested_point_deformation_blender.py
(or paste into Blender's Scripting workspace), then press Play.

Verified against real bpy (PyPI's headless module, see tests/blender/) by
simulating scene.frame_set() calls -- not separately verified against
real interactive Play/scrubbing in a windowed session, which is a
related but distinct claim (see CLAUDE.md's Testing status section).
"""

import math

import bpy

from d3blender import select, scale_band
from d3blender.blender_adapter import get_adapter, live_point_data

FPS = 24
FRAMES = range(1, 25)


def make_sphere_shape(n=8, radius=1.0):
    verts = []
    for i in range(n):
        theta = math.pi * (i / (n - 1))
        for j in range(n):
            phi = 2 * math.pi * (j / n)
            verts.append((
                radius * math.sin(theta) * math.cos(phi),
                radius * math.sin(theta) * math.sin(phi),
                radius * math.cos(theta),
            ))
    return verts


def spawn_points(collection, name, vertices):
    # The Blender-specific stand-in for mock.spawn_points() -- real mesh
    # creation, which d3blender deliberately doesn't wrap (see CLAUDE.md).
    mesh = bpy.data.meshes.new(f'{name}Mesh')
    mesh.from_pydata(vertices, [], [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


spheres_data = [
    {'label': 'a', 'amplitude': 0.15, 'phase': 0.0},
    {'label': 'b', 'amplitude': 0.20, 'phase': 1.2},
]

x = scale_band([d['label'] for d in spheres_data], range_=(0, 4), padding=0.3)

adapter = get_adapter()
chart = adapter.get_or_create_collection('Chart')

balls = (select(adapter, '#Chart mesh')
         .data(spheres_data, key=lambda i, d: d['label'])
         .join(enter=lambda d: spawn_points(chart, f"ball_{d['label']}", make_sphere_shape())))

for el, d in zip(balls.elements, spheres_data):
    el.location = (x(d['label']), 0, 1.5)
    el['amplitude'] = d['amplitude']
    el['phase'] = d['phase']

by_label = {d['label']: el for el, d in zip(balls.elements, spheres_data)}


def make_breathing_fn(base_shape, amplitude, phase):
    def position(frame):
        t = frame / FPS
        scale = 1.0 + amplitude * math.sin(t * 2 * math.pi + phase)
        return [(vx * scale, vy * scale, vz * scale) for vx, vy, vz in base_shape]
    return position


def make_orbit_fn(n_verts, phase):
    def position(frame):
        t = frame / FPS
        return [
            (0.5 * math.cos(t + phase + i), 0.5 * math.sin(t + phase + i), i / n_verts - 0.5)
            for i in range(n_verts)
        ]
    return position


bpy.context.scene.frame_end = FRAMES[-1]  # so Play loops a meaningful (1-second) range

ball_a = by_label['a']
ball_b = by_label['b']

base_shape_a = adapter.point_attr(ball_a, 'position')
breathe_a = make_breathing_fn(base_shape_a, ball_a['amplitude'], ball_a['phase'])
orbit_b = make_orbit_fn(adapter.point_count(ball_b), ball_b['phase'])

# LIVE, not baked: registers a frame_change_pre handler per sphere and
# applies frame 1 immediately. Safe to re-run this whole script while
# iterating -- re-registering for the same object replaces its handler
# rather than stacking a duplicate on top (see live_point_data's
# docstring). Hang onto the stop() functions if you want to remove a
# binding later -- e.g. before deleting a sphere, so its handler doesn't
# outlive it.
stop_a = live_point_data(adapter, ball_a, position=breathe_a)
stop_b = live_point_data(adapter, ball_b, position=orbit_b)

for el in balls.elements:
    v0 = adapter.point_attr(el, 'position')[0]
    print(f"{el.name}: object loc={tuple(el.location)}, "
          f"vertex[0] local co=({v0[0]:.2f}, {v0[1]:.2f}, {v0[2]:.2f}) "
          f"at frame {bpy.context.scene.frame_current} -- now press Play")
