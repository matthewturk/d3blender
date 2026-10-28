"""
points.py -- the d3-flavored "bind data to a mesh's vertices" layer,
sitting on top of adapter.point_attr()/set_point_attr() the way axis.py
sits on top of create_line_mesh(): pure orchestration, no bpy, testable
against the mock exactly like everything else here.

Deliberately NOT shaped like Join. Join needs a stamped identity
(d3_key) because objects can be individually added/removed, and a rerun
needs to recognize "this object still represents the same thing" (see
CLAUDE.md). Vertices don't have that kind of identity to begin with --
point_data() binds by *index* (data[i] -> vertex i), not by key, and
never resizes the mesh to fit (see set_point_attr's docstring). If you
need per-entity continuity across a changing dataset -- something
enters, something exits, existing ones keep their identity -- that's
what the object-based Selection/Join is for; point_data() trades
identity for the scale vertices give you over one-object-per-datum.
"""


def point_data(adapter, el, frame, **channels):
    """Compute and bulk-write one or more per-vertex channels on `el`.

    Each keyword is a channel name (`'position'`, or any custom
    point-attribute name -- see set_point_attr()) mapped to a callable
    `fn(frame) -> values`, one value per vertex, called once per channel
    per call (not once per vertex -- keep the per-vertex work inside
    `fn` itself, e.g. a list comprehension, so this stays one bulk write
    per channel rather than a Python loop of individual .attr() calls):

        point_data(adapter, ball, current_frame,
                   position=lambda frame: [...])

    `frame` is handed to every channel function unchanged and otherwise
    unexamined -- point_data() doesn't know or care whether it's an
    animation frame, a plain step counter, or anything else; that's the
    caller's concept, not this function's.

    There's no keyframing, no interpolation, and no state kept between
    calls here -- every call recomputes and overwrites each channel from
    scratch. That's deliberate, not a missing feature: per-vertex F-curve
    keyframes are real but cost scales with vertex count (measured
    against tests/blender/ -- fine for a few hundred points, real file
    bloat past that), and per-vertex custom attributes can't be
    keyframed through bpy's RNA system at all (also verified there). If
    a channel needs continuity across calls -- easing between two
    explicit states, holding a lookup table -- give its function that
    state via a closure and manage it yourself; point_data() only ever
    asks each channel "what's the value right now."

    Returns `el`, so a call composes into a `.each()`/loop the same way
    everything else here does.
    """
    for name, fn in channels.items():
        adapter.set_point_attr(el, name, fn(frame))
    return el
