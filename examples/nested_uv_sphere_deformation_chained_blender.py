"""
nested_uv_sphere_deformation_blender.py, restructured to read closer to
idiomatic d3: one long operator chain (select -> select -> data -> join
-> attr -> attr -> attr -> each -> each), start to finish, nothing
before or after it -- instead of separate imperative for-loops,
accessor functions instead of direct attribute assignment,
scale_ordinal() for categorical dispatch instead of an ad hoc dict,
live_point_data()'s frame_change_pre wiring standing in for d3's own
event-driven callbacks (.on(), a force simulation's .on('tick', ...)),
and `.join('uv_sphere', collection=chart)` -- real d3's own
`selection.join("circle")` shorthand -- instead of a hand-written
spawn_uv_sphere() helper (see Join.join()'s docstring in selection.py).
One note on that last one: the shorthand's registry default sphere
resolution (segments=32, ring_count=16) is denser than this file's old
hand-written helper (16, 8), so vertex/face counts are higher than an
earlier run of this file would have shown -- the deformation math
itself is unaffected, only visual smoothness. Same scene otherwise,
same math, same result as the other file -- only the shape of the code
changes.

**The gap this file used to have to work around is now closed.** Real
d3 accessor functions are `(d, i) => ...` -- they receive the bound
datum itself, because a d3 selection keeps `__data__` attached to each
DOM node once bound. d3blender's `Selection` now does the equivalent:
`Join.join()` tracks each entered/updated element's own datum alongside
it (`Selection.datum`, parallel to `.elements`), and `.attr()`/`.each()`/
`.keyframe()`/`.filter()` all accept an `(el, d, i)` callable -- see
selection.py's `Selection.datum` and `_invoke()`. So the chain below
reads `d['label']`/`d['amplitude']`/`d['phase']` directly, the same way
real d3 would, rather than closing over `spheres_data` and indexing by
`i` (which is what this file did before, and what plain `(el, i)`
callables still have to do -- both shapes keep working, chosen by a
callable's own arity, so nothing using the old style broke).

Run: blender --python examples/nested_uv_sphere_deformation_chained_blender.py
(or paste into Blender's Scripting workspace), then press Play.

Verified against real bpy the same way as nested_uv_sphere_deformation_blender.py
(see tests/blender/) -- this file produces the identical scene, just
built differently.
"""

import math

import bpy

from d3blender import select, scale_band, scale_ordinal
from d3blender.blender_adapter import get_adapter, live_point_data

FPS = 24
FRAMES = range(1, 25)

spheres_data = [
    {'label': 'a', 'amplitude': 0.15, 'phase': 0.0},   # "breathing": uniform scale
    {'label': 'b', 'amplitude': 0.08, 'phase': 1.2},   # "ripple": per-vertex, own rest height
]

x = scale_band([d['label'] for d in spheres_data], range_=(0, 4), padding=0.3)


# -- the two deformation styles, unchanged from the earlier demo --------
def make_breathing_fn(base_shape, amplitude, phase):
    def position(frame):
        t = frame / FPS
        scale = 1.0 + amplitude * math.sin(t * 2 * math.pi + phase)
        return [(vx * scale, vy * scale, vz * scale) for vx, vy, vz in base_shape]
    return position


def make_ripple_fn(base_shape, amplitude, phase):
    def position(frame):
        t = frame / FPS
        return [
            (vx, vy, vz + amplitude * math.sin(t * 2 * math.pi + phase + vz * 3))
            for vx, vy, vz in base_shape
        ]
    return position


# scale_ordinal() as categorical dispatch: picking a deformer by label
# is exactly the same shape of problem as picking a color by category --
# d3's most common use for an ordinal scale, just with functions instead
# of colors as the range.
deformer_for = scale_ordinal([d['label'] for d in spheres_data],
                             range_=[make_breathing_fn, make_ripple_fn])

adapter = get_adapter()
chart = adapter.get_or_create_collection('Chart')
bpy.context.scene.frame_end = FRAMES[-1]  # so Play loops a meaningful (1-second) range


def wire_up(el, d, i):
    """The .each() escape hatch -- d3's own answer for "do something
    per-element that isn't just setting one attribute" (real d3 code
    reaches for .each() to register a .on() handler per element for the
    same reason). `d` is this sphere's own bound datum, handed straight
    to us -- no re-indexing into spheres_data needed. Captures this
    sphere's own rest shape and registers its live deformation. Doesn't
    keep the stop() handle -- see nested_uv_sphere_deformation_blender.py
    if you want to hang onto one for teardown."""
    base_shape = adapter.point_attr(el, 'position')
    deform = deformer_for(d['label'])(base_shape, d['amplitude'], d['phase'])
    live_point_data(adapter, el, position=deform)


def report(el, i):
    # The plain (el, i) shape still works fine too -- this one doesn't
    # need the datum, so it doesn't ask for it. Both call shapes coexist
    # freely.
    print(f"{el.name}: object loc={tuple(el.location)}, "
          f"{adapter.point_count(el)} vertices / {len(el.data.polygons)} faces, "
          f"at frame {bpy.context.scene.frame_current} -- now press Play")


# -- one chain, start to finish: select -> select -> data -> join -----
#    -> attr -> attr -> attr -> each -> each. select(adapter, chart) wraps
#    the known collection (like d3.select(node)); the chained
#    .select('mesh') is the scoped query within it -- an actual chained
#    select, not one opaque combined selector string, matching real d3's
#    own d3.select(parent).selectAll(child) shape. Every accessor below
#    is (el, d, i) -- d is this element's own bound datum, the same
#    shape real d3's (d, i) => ... accessors receive.
balls = (
    select(adapter, chart)
    .select('mesh')
    .data(spheres_data, key=lambda i, d: d['label'])
    .join('uv_sphere', collection=chart)
    .attr('name', lambda el, d, i: f"ball_{d['label']}")
    .attr('location', lambda el, d, i: (x(d['label']), 0, 1.5))
    .attr('amplitude', lambda el, d, i: d['amplitude'])
    .attr('phase', lambda el, d, i: d['phase'])
    .each(wire_up)
    .each(report)
)
