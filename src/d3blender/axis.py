"""
axis.py — the "ticks are just a set of lines" version of d3's
axisBottom()/axisLeft(): no domain baseline, no tick-label text, just a
short line segment per tick value. Pure geometry math -- no bpy, no
adapter -- see adapter.SceneAdapter.create_line_mesh() for turning the
result into an actual object.

d3blender charts don't share one fixed 2D plane the way an SVG axis can
assume (bar_chart.py stands bars up along z at y=0; scatter_plot.py lies
flat at z=0), so this doesn't hardcode which spatial axis is "the" x or
y. `place` and `tick_vector` are how the caller supplies that
convention -- see their docstrings below.
"""


def ticks(domain, count=10):
    """`count` evenly spaced values spanning `domain` -- a simple
    fallback, not d3's "nice" rounded tick values (same stated
    simplification as array.bin(), for the same reason: fine for
    drawing, not for guaranteeing the values land on round numbers)."""
    lo, hi = domain
    if count <= 1:
        return [lo]
    step = (hi - lo) / (count - 1)
    return [lo + i * step for i in range(count)]


def tick_lines(scale, values, place, tick_vector):
    """One line segment per tick value: from `place(scale(v))` (a point
    on the axis baseline) to that point offset by `tick_vector` (the
    perpendicular mark). Returns a list of (p0, p1) 3-tuples, ready for
    `SceneAdapter.create_line_mesh()`.

    `place(pos) -> (x, y, z)` maps the scale's 1D output onto the plane
    your chart actually lives in; `tick_vector` is a fixed `(dx, dy, dz)`
    offset describing which way the marks point and how long they are.
    Both are the caller's job, not this function's -- that convention
    differs per chart (see module docstring).
    """
    segments = []
    for v in values:
        p0 = place(scale(v))
        p1 = tuple(a + b for a, b in zip(p0, tick_vector))
        segments.append((p0, p1))
    return segments
