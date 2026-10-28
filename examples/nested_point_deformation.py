"""
Layers point_data()/point_attr() (per-vertex) underneath Selection/Join
(per-object) -- two independent levels of "position", composed:

  level 1 (object)  -- WHERE each sphere sits in the world. Ordinary
                       d3blender: a data array, scale_band() for layout,
                       .data().join() to create one object per sphere.
  level 2 (mesh)     -- WHAT SHAPE each sphere's own mesh has, entirely
                       in that object's LOCAL space. point_data() drives
                       this per frame, per sphere.

Nothing here mixes the two spaces, because Blender itself doesn't:
vertex .co is *always* local to its own object; an object's .location
is added on top by Blender when it works out where a vertex ends up in
the world. So moving a sphere (level 1) and reshaping it (level 2) are
independent -- you can change either without the other knowing.

The two spheres below deliberately use DIFFERENT deformation styles, to
show the distinction the shape of a formula makes, not just its
inputs:

  - ball_a is RELATIVE: its per-frame shape is captured-base-shape
    scaled by a factor -- "the rest shape, displaced". This is what
    you want when there's a design/rest state you're perturbing.
  - ball_b is STRICTLY LOCAL / absolute: its per-frame shape is
    computed from scratch every call, straight from each vertex's
    index and the frame -- no reference to any prior or base state at
    all. This is what you want for a pure formula with no "rest" to
    speak of.

Both are still local-only in the Blender sense (vertex .co, not world
position) -- "relative" here means "relative to a captured base shape",
not "relative to the object's world location". If you ever needed a
vertex's *world*-space target, you'd subtract the object's own
.location yourself first -- point_data()/point_attr() never do that
conversion for you (see the loop below).

The "multi-level functional" part: make_breathing_fn() is a function
that *returns* a function -- called once per sphere, closing over that
sphere's own base shape and its own per-instance parameters (amplitude,
phase, both ordinary d3blender data), producing a distinct fn(frame)
for each sphere from the same formula. That returned function is what
point_data() calls, once per frame, per sphere.

Run: python examples/nested_point_deformation.py
"""

import math

from d3blender import select, scale_band
from d3blender.mock import new_scene, spawn_points
from d3blender.points import point_data

FPS = 24
FRAMES = range(1, 25)  # one second, for the printed summary below


def make_sphere_shape(n=8, radius=1.0):
    """A crude UV-sphere as a flat list of (x, y, z) points -- purely
    local, centered on the object's own origin. Nothing here knows or
    cares where the object itself will end up sitting in the world."""
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


# --- level 1: per-instance data, one entry per sphere -------------------
spheres_data = [
    {'label': 'a', 'amplitude': 0.15, 'phase': 0.0},
    {'label': 'b', 'amplitude': 0.20, 'phase': 1.2},
]

x = scale_band([d['label'] for d in spheres_data], range_=(0, 4), padding=0.3)

adapter, chart = new_scene('Chart')

balls = (select(adapter, '#Chart mesh')
         .data(spheres_data, key=lambda i, d: d['label'])
         .join(enter=lambda d: spawn_points(
             adapter, chart, f"ball_{d['label']}", vertices=make_sphere_shape())))

for el, d in zip(balls.elements, spheres_data):
    el.location = (x(d['label']), 0, 1.5)  # object-level WORLD position, from data
    el['amplitude'] = d['amplitude']
    el['phase'] = d['phase']

by_label = {d['label']: el for el, d in zip(balls.elements, spheres_data)}


# --- level 2a: RELATIVE -- displace a captured base/rest shape ----------

def make_breathing_fn(base_shape, amplitude, phase):
    """Returns fn(frame) closing over THIS sphere's own base shape and
    its own amplitude/phase -- two spheres calling this with different
    per-instance data get two independent closures from one formula."""
    def position(frame):
        t = frame / FPS
        scale = 1.0 + amplitude * math.sin(t * 2 * math.pi + phase)
        return [(vx * scale, vy * scale, vz * scale) for vx, vy, vz in base_shape]
    return position


# --- level 2b: STRICTLY LOCAL -- computed from scratch, no base shape ---

def make_orbit_fn(n_verts, phase):
    """Returns fn(frame) that computes each vertex's local position
    directly from its own index and the frame -- there's no captured
    rest shape here to perturb, just a formula."""
    def position(frame):
        t = frame / FPS
        return [
            (0.5 * math.cos(t + phase + i), 0.5 * math.sin(t + phase + i), i / n_verts - 0.5)
            for i in range(n_verts)
        ]
    return position


ball_a = by_label['a']
ball_b = by_label['b']

base_shape_a = adapter.point_attr(ball_a, 'position')  # ball_a's OWN rest shape, local
breathe_a = make_breathing_fn(base_shape_a, ball_a['amplitude'], ball_a['phase'])
orbit_b = make_orbit_fn(adapter.point_count(ball_b), ball_b['phase'])

for frame in FRAMES:
    # LOCAL: point_data only ever touches vertex.co, which Blender treats
    # as relative to each object's own origin -- moving an object
    # (.location) and reshaping its mesh (point_data) compose for free,
    # neither has to know about the other.
    point_data(adapter, ball_a, frame, position=breathe_a)
    point_data(adapter, ball_b, frame, position=orbit_b)

if __name__ == '__main__':
    for el in balls.elements:
        v0 = adapter.point_attr(el, 'position')[0]
        print(f"{el.name}: object loc={el.location}, "
              f"vertex[0] local co=({v0[0]:.2f}, {v0[1]:.2f}, {v0[2]:.2f}) "
              f"at frame {FRAMES[-1]}")
