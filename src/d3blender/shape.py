"""
shape.py -- the "connect these points into a path" piece of d3-shape,
scoped to exactly what SceneAdapter.create_line_mesh() needs: pure
geometry math, no bpy, no adapter (same shape as axis.py). d3.line()'s
actual job isn't "generate a primitive" -- the thing this project
deliberately doesn't do (see CLAUDE.md's "no primitive-mesh functions"
discussion) -- it's turning a data-derived array of points into a path,
a different thing: the points already come from your own data/formula,
this only decides which ones connect to which.
"""


def line(points, closed=False):
    """One segment per consecutive pair of points, ready for
    SceneAdapter.create_line_mesh(collection, name, segments) -- the
    shape d3.line() produces (a polyline through your points), not
    axis.tick_lines()'s independent, unconnected tick marks. `closed`
    also connects the last point back to the first (d3's
    curveLinearClosed) -- for a closed loop/polygon outline instead of
    an open path. Fewer than two points has no segments to draw."""
    points = list(points)
    if len(points) < 2:
        return []
    segments = [(points[i], points[i + 1]) for i in range(len(points) - 1)]
    if closed:
        segments.append((points[-1], points[0]))
    return segments
