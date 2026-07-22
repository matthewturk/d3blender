"""
Scatter plot: two independent linear scales, one per axis -- the same
idea as the D3 exoplanet chart, just placing cubes instead of SVG circles.
Plus axis ticks: d3blender's ticks are just line segments (no domain
baseline, no tick-label text -- see d3blender/axis.py), all held in one
mesh object per axis rather than one object per tick.
Run: python examples/scatter_plot.py
"""

from d3blender import select, scale_linear, scale_ordinal
from d3blender.axis import ticks, tick_lines
from d3blender.mock import new_scene, spawn

adapter, chart = new_scene('Chart')

points = [
    {'id': 0, 'period': 4.2, 'radius': 15.6, 'method': 'transit'},
    {'id': 1, 'period': 130, 'radius': 1.17, 'method': 'transit'},
    {'id': 2, 'period': 11.2, 'radius': 1.07, 'method': 'radial_velocity'},
]

px = scale_linear(domain=(0, 150), range_=(-5, 5))
py = scale_linear(domain=(0, 20), range_=(0, 5))
color = scale_ordinal(['transit', 'radial_velocity'], range_=['#E8B75D', '#5B8DEF'])

scatter = (select(adapter, '#Chart mesh')
           .data(points, key=lambda i, d: d['id'])
           .join(enter=lambda d: spawn(adapter, chart, f"pt_{d['id']}")))

for el, d in zip(scatter.elements, points):
    el.location = (px(d['period']), py(d['radius']), 0)
    el.scale = (0.15, 0.15, 0.15)
    el['fill'] = color(d['method'])

# Both axes lie flat at z=0 -- the x-axis baseline runs along y=0, the
# y-axis baseline runs along x=-5 (the left edge of px's range). Ticks
# point away from the plotted data (-y and -x respectively).
x_axis = tick_lines(px, ticks(domain=(0, 150), count=6),
                     place=lambda p: (p, 0, 0), tick_vector=(0, -0.3, 0))
y_axis = tick_lines(py, ticks(domain=(0, 20), count=5),
                     place=lambda p: (-5, p, 0), tick_vector=(-0.3, 0, 0))
adapter.create_line_mesh(chart, 'x_ticks', x_axis)
adapter.create_line_mesh(chart, 'y_ticks', y_axis)

if __name__ == '__main__':
    scatter.each(lambda el, i: print(
        f"{el.name}: loc={tuple(round(v, 2) for v in el.location)} fill={el['fill']}"))
    print(f"x_ticks: {len(x_axis)} segments, y_ticks: {len(y_axis)} segments")
