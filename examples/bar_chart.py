"""
Bar chart: one cube per data point, height and spacing driven by scales.
Run: python examples/bar_chart.py
(swap the mock for d3blender.blender_adapter.get_adapter() to run for real)
"""

from d3blender import select, scale_linear, scale_band, scale_ordinal
from d3blender.adapter import SceneAdapter
from d3blender.mock import MockObject, MockCollection

chart = MockCollection('Chart')
adapter = SceneAdapter(objects=[], collections=[chart])


def add_cube(name):
    """Stand-in for bpy.ops.mesh.primitive_cube_add() + rename, or
    databpy's db.create_object('CUBE', name=name)."""
    o = MockObject(name, 'MESH')
    chart.objects.append(o)
    o.users_collection = (chart,)
    adapter.objects.append(o)
    return o


data = [
    {'label': 'Jan', 'revenue': 12},
    {'label': 'Feb', 'revenue': 18},
    {'label': 'Mar', 'revenue': 9},
    {'label': 'Apr', 'revenue': 24},
]

x = scale_band([d['label'] for d in data], range_=(0, 8), padding=0.2)
height = scale_linear(domain=(0, 24), range_=(0.2, 4.0))
color = scale_ordinal([d['label'] for d in data],
                       range_=['#E8B75D', '#5B8DEF', '#5DE8A6', '#E85D9E'])

bars = (select(adapter, '#Chart mesh')
        .data(data, key=lambda i, d: d['label'])
        .join(enter=lambda d: add_cube(f"bar_{d['label']}")))

for el, d in zip(bars.elements, data):
    h = height(d['revenue'])
    el.location = (x(d['label']), 0, h / 2)          # sits on the ground, grows up
    el.scale = (x.bandwidth() / 2, 0.5, h / 2)        # cube default is 2x2x2, halve for unit scale
    el['revenue'] = d['revenue']
    el['fill'] = color(d['label'])

if __name__ == '__main__':
    bars.each(lambda el, i: print(f"{el.name}: loc={el.location} scale={el.scale} fill={el['fill']}"))
