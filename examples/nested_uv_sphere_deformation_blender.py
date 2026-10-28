"""
nested_point_deformation.py, but the spheres are built from real
Blender UV-sphere primitives (bpy.ops.mesh.primitive_uv_sphere_add())
instead of a hand-rolled point cloud -- see CLAUDE.md/README's "no
primitive-mesh functions" discussion for why d3blender doesn't build
this geometry itself: correct topology (poles, quad rings, actual
edges/faces) is exactly what Blender's own primitive operators already
do well. point_attr()/point_data() don't care how a mesh was built,
though, which is the thing worth showing here -- they drive a real UV
sphere's vertices exactly the same way they drove the previous demo's
bare point cloud.

Real-bpy only -- bpy.ops.mesh.primitive_uv_sphere_add() is an operator;
mock.py has no bpy.ops at all, by design (see CLAUDE.md), so unlike
nested_point_deformation.py this one has no mock-based sibling to run
without Blender.

**A real, connected mesh changes what "strictly local" safely means.**
The flat point cloud in nested_point_deformation.py had no edges at
all, so ball_b there could move every vertex on its own totally
independent path with no ill effect -- it was never anything but a
cloud of floating points. A UV sphere's vertices *are* connected by real
edges and faces, and this library doesn't help you build or maintain
that topology (see CLAUDE.md) -- so a formula that moves neighboring
vertices in unrelated directions will visibly tear and self-intersect
the surface. ball_b here is adapted accordingly: still stateless, still
recomputed fresh every frame (no captured "previous frame" anywhere),
but driven by each vertex's *own rest position* (its original height)
rather than being independent of it -- nearby vertices have nearby rest
heights, so they move together, and the surface stays coherent. That's
the actual lesson this variant adds: getting a "nice looking" result
out of point_data on a real mesh is about respecting the topology you
started with, not about d3blender managing edges for you.

Like nested_point_deformation_blender.py, this drives the deformation
with live_point_data(), not a bake loop -- **press Play or scrub the
timeline after running this** to actually see the spheres breathe/
ripple; running the script itself only registers the bindings and
applies frame 1.

Run: blender --python examples/nested_uv_sphere_deformation_blender.py
(or paste into Blender's Scripting workspace), then press Play.

Verified against real bpy (PyPI's headless module, see tests/blender/):
confirmed two independently created/renamed/relinked UV spheres don't
cross-contaminate, and confirmed a fresh UV sphere's vertices are
read/written by point_attr/point_data/live_point_data with no changes
needed there, by simulating scene.frame_set() calls -- not separately
verified against real interactive Play/scrubbing in a windowed session,
which is a related but distinct claim (see CLAUDE.md's Testing status
section), nor yet against the full Blender application generally.
"""

import math

import bpy

from d3blender import select, scale_band
from d3blender.blender_adapter import get_adapter, live_point_data

FPS = 24
FRAMES = range(1, 25)


def spawn_uv_sphere(collection, name, radius=1.0, segments=16, ring_count=8):
    """The Blender-specific, real-topology stand-in for
    nested_point_deformation.py's make_sphere_shape() + spawn_points() --
    a real UV sphere (proper poles, quad rings, actual faces), relinked
    into `collection` the same way scatter_plot_3d_blender.py's
    spawn_sphere() does it. This is the "nice looking objects" answer:
    d3blender doesn't build this geometry, Blender's own operator does,
    and point_attr/point_data don't need to know the difference."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=segments, ring_count=ring_count)
    obj = bpy.context.active_object
    obj.name = name
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


# --- level 1: per-instance data, one entry per sphere -------------------
spheres_data = [
    {'label': 'a', 'amplitude': 0.15, 'phase': 0.0},
    {'label': 'b', 'amplitude': 0.08, 'phase': 1.2},
]

x = scale_band([d['label'] for d in spheres_data], range_=(0, 4), padding=0.3)

adapter = get_adapter()
chart = adapter.get_or_create_collection('Chart')

balls = (select(adapter, '#Chart mesh')
         .data(spheres_data, key=lambda i, d: d['label'])
         .join(enter=lambda d: spawn_uv_sphere(chart, f"ball_{d['label']}")))

for el, d in zip(balls.elements, spheres_data):
    el.location = (x(d['label']), 0, 1.5)  # object-level WORLD position, from data
    el['amplitude'] = d['amplitude']
    el['phase'] = d['phase']

by_label = {d['label']: el for el, d in zip(balls.elements, spheres_data)}


# --- level 2a: RELATIVE / uniform -- scale a captured base shape --------
# Safe on any topology: a uniform scale is a similarity transform, so it
# can never tear a connected mesh no matter how it's built.

def make_breathing_fn(base_shape, amplitude, phase):
    """Returns fn(frame) closing over THIS sphere's own base shape and
    its own amplitude/phase, same as the point-cloud demo."""
    def position(frame):
        t = frame / FPS
        scale = 1.0 + amplitude * math.sin(t * 2 * math.pi + phase)
        return [(vx * scale, vy * scale, vz * scale) for vx, vy, vz in base_shape]
    return position


# --- level 2b: PER-VERTEX -- driven by each vertex's own rest position --
# The connected-mesh-safe replacement for the point-cloud demo's fully
# independent "orbit" style: still stateless and recomputed from
# scratch every frame, but the input to the formula is each vertex's
# own rest height (captured once, from base_shape), not its raw index
# and not an accumulated displacement -- so neighboring vertices, which
# started at similar heights, move together instead of tearing apart.

def make_ripple_fn(base_shape, amplitude, phase):
    def position(frame):
        t = frame / FPS
        return [
            (vx, vy, vz + amplitude * math.sin(t * 2 * math.pi + phase + vz * 3))
            for vx, vy, vz in base_shape
        ]
    return position


bpy.context.scene.frame_end = FRAMES[-1]  # so Play loops a meaningful (1-second) range

ball_a = by_label['a']
ball_b = by_label['b']

base_shape_a = adapter.point_attr(ball_a, 'position')  # ball_a's OWN rest shape, local
base_shape_b = adapter.point_attr(ball_b, 'position')  # ball_b's OWN rest shape, local
breathe_a = make_breathing_fn(base_shape_a, ball_a['amplitude'], ball_a['phase'])
ripple_b = make_ripple_fn(base_shape_b, ball_b['amplitude'], ball_b['phase'])

# LIVE, not baked -- see live_point_data's docstring. Re-running this
# whole script (e.g. while iterating in the Scripting workspace) is
# safe: re-registering for the same object replaces its handler rather
# than stacking a duplicate.
stop_a = live_point_data(adapter, ball_a, position=breathe_a)
stop_b = live_point_data(adapter, ball_b, position=ripple_b)

for el in balls.elements:
    v0 = adapter.point_attr(el, 'position')[0]
    print(f"{el.name}: object loc={tuple(el.location)}, "
          f"{adapter.point_count(el)} vertices / {len(el.data.polygons)} faces (real topology), "
          f"vertex[0] local co=({v0[0]:.2f}, {v0[1]:.2f}, {v0[2]:.2f}) "
          f"at frame {bpy.context.scene.frame_current} -- now press Play")
