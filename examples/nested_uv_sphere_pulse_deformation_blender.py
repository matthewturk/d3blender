"""
A new deformation style for the nested_uv_sphere_deformation_*.py
family: a radial pulse that travels outward across each sphere's
surface from a per-sphere source point, instead of
nested_uv_sphere_deformation_blender.py's uniform "breathing" or
static-phase "ripple". Same underlying principles as those two (real
UV-sphere primitives, point_attr/point_data driving vertex positions in
local space, live_point_data for live scrub/Play-driven updates,
Selection.datum for (el, d, i) chained accessors -- see
nested_uv_sphere_deformation_chained_blender.py) -- this is a
genuinely new formula and a richer dataset (four spheres instead of
two, each with its own source point), not a rewrite of the existing
ones.

**The pulse formula, in a sentence:** each vertex is displaced along its
own rest-space normal by an amount depending on its great-circle
angular distance from a chosen "source" point on the sphere and the
current frame -- so ridges appear to expand outward from the source
across the surface over time, like a ripple spreading from a point
dropped in water, wrapped onto a sphere. Verified (see the angle/
displacement table below, checked by hand before writing this file):
a vertex right at the source and one at 180 degrees from it oscillate
completely out of phase with each other, and the peak/trough pattern
visibly shifts outward across intermediate angles as frame increases --
a real traveling wave, not a static one.

    angle=  0.0deg  frames 1,6,12,18,24 -> -0.006, -0.035, -0.068, -0.094, -0.112
    angle= 45.0deg  frames 1,6,12,18,24 ->  0.114,  0.102,  0.078,  0.048,  0.013
    angle= 90.0deg  frames 1,6,12,18,24 ->  0.065,  0.088,  0.108,  0.119,  0.119
    angle=180.0deg  frames 1,6,12,18,24 -> -0.107, -0.117, -0.120, -0.112, -0.094

Still stateless and topology-safe the same way nested_uv_sphere_deformation_blender.py's
ripple is: displacement is a pure function of (frame, this vertex's own
rest position), never of a previous frame or another vertex's motion,
and neighboring vertices (similar angular distance from the source)
move together, not independently -- see CLAUDE.md/README for why that
matters on a real, connected mesh.

Also uses `.join('uv_sphere', collection=chart)` instead of a hand-
written spawn_uv_sphere() helper -- Join.join()'s new shape-name
shorthand (real d3's own `selection.join("circle")`, dispatched through
`LiveBlenderAdapter.creator()`; see selection.py's Join.join()
docstring). One real wall worth knowing if you reach for this
yourself: shape parameters (radius, segments, ring_count) only exist as
creation-time arguments, never as settable attributes afterward --
`obj['segments'] = 32` on an already-created sphere changes nothing
about its geometry (confirmed in tests/blender/test_join_creator.py).
Genuinely mutable properties still work as ordinary `.attr()` calls
after the join, exactly as before -- see `.attr('name', ...)` and
`.attr('location', ...)` below.

Run: blender --python examples/nested_uv_sphere_pulse_deformation_blender.py
(or paste into Blender's Scripting workspace), then press Play.

Verified against real bpy (PyPI's headless module, see tests/blender/)
by simulating scene.frame_set() calls and checking the displacement
math directly -- not separately verified against real interactive
Play/scrubbing in a windowed session or the full Blender application
(see CLAUDE.md's Testing status section).
"""

import math

import bpy

from d3blender import select, scale_band
from d3blender.blender_adapter import get_adapter, live_point_data

FPS = 24
FRAMES = range(1, 49)  # two seconds -- a slower pulse reads better with more room to travel

# Four spheres, each pulsing outward from a different point on its own
# surface -- north/south poles, and two points on the equator -- with
# its own amplitude/speed/wavelength. Richer than the two-sphere demos:
# this is meant to look like real, varied dataset-driven behavior, not
# just two hardcoded styles.
spheres_data = [
    {'label': 'north', 'source': (0.0, 0.0, 1.0), 'amplitude': 0.12, 'speed': 1.2, 'wavelength': 0.6},
    {'label': 'east', 'source': (1.0, 0.0, 0.0), 'amplitude': 0.08, 'speed': 0.8, 'wavelength': 0.9},
    {'label': 'south', 'source': (0.0, 0.0, -1.0), 'amplitude': 0.15, 'speed': 1.6, 'wavelength': 0.4},
    {'label': 'equator', 'source': (0.0, 1.0, 0.0), 'amplitude': 0.10, 'speed': 1.0, 'wavelength': 0.7},
]

x = scale_band([d['label'] for d in spheres_data], range_=(0, 8), padding=0.3)


def make_pulse_fn(base_shape, source, amplitude, speed, wavelength):
    """Returns fn(frame) closing over this sphere's own rest shape and
    its own source point/amplitude/speed/wavelength -- a distinct
    closure per sphere from the same formula, same pattern as
    make_breathing_fn/make_ripple_fn in the other demos."""
    sx, sy, sz = source

    def position(frame):
        t = frame / FPS
        out = []
        for vx, vy, vz in base_shape:
            r = math.sqrt(vx * vx + vy * vy + vz * vz) or 1e-9
            nx, ny, nz = vx / r, vy / r, vz / r
            cos_angle = max(-1.0, min(1.0, nx * sx + ny * sy + nz * sz))
            angle = math.acos(cos_angle)  # 0 at the source point, pi at its antipode
            displacement = amplitude * math.sin(angle / wavelength - t * speed)
            out.append((vx + displacement * nx, vy + displacement * ny, vz + displacement * nz))
        return out
    return position


adapter = get_adapter()
chart = adapter.get_or_create_collection('Chart')
bpy.context.scene.frame_end = FRAMES[-1]  # so Play loops a meaningful (2-second) range


def wire_up(el, d, i):
    """Captures this sphere's own rest shape and registers its own
    pulse, sourced from its own datum -- see
    nested_uv_sphere_deformation_chained_blender.py for why this is
    (el, d, i), not (el, i) plus manual re-indexing. Doesn't keep the
    stop() handle -- if you need to tear a binding down later, hang
    onto it yourself the way nested_uv_sphere_deformation_blender.py
    does (stop_a = live_point_data(...)); nothing here needs it."""
    base_shape = adapter.point_attr(el, 'position')
    deform = make_pulse_fn(base_shape, d['source'], d['amplitude'], d['speed'], d['wavelength'])
    live_point_data(adapter, el, position=deform)


def report(el, i):
    print(f"{el.name}: object loc={tuple(el.location)}, "
          f"{adapter.point_count(el)} vertices / {len(el.data.polygons)} faces, "
          f"at frame {bpy.context.scene.frame_current} -- now press Play")


# -- one chain, start to finish: select -> select -> data -> join -----
#    -> attr -> attr -> attr -> each -> each. select(adapter, chart)
#    wraps the known collection (like d3.select(node)); the chained
#    .select('mesh') is the scoped query within it. join('uv_sphere',
#    collection=chart) is the enter='shape name' shorthand (see
#    Join.join()'s docstring / LiveBlenderAdapter.creator()) -- real
#    d3's own selection.join("circle"), just with an explicit
#    `collection=` since Blender objects need one and there's no DOM-like
#    implicit parent to infer it from. Everything genuinely mutable --
#    name, location, custom props -- is still an ordinary .attr() call
#    afterward, exactly as before; only the one-time creation call
#    (previously the hand-written spawn_uv_sphere() helper) changed.
balls = (
    select(adapter, chart)
    .select('mesh')
    .data(spheres_data, key=lambda i, d: d['label'])
    .join('uv_sphere', collection=chart)
    .attr('name', lambda el, d, i: f"ball_{d['label']}")
    .attr('location', lambda el, d, i: (x(d['label']), 0, 1.5))
    .attr('amplitude', lambda el, d, i: d['amplitude'])
    .each(wire_up)
    .each(report)
)
