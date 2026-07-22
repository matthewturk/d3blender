"""
Classic d3 update pattern: rerun with changed data and the scene
reconciles instead of rebuilding -- new items enter, changed items
animate to their new state, removed items exit.
Run: python examples/update_pattern.py
"""

from d3blender import select, scale_linear, scale_band
from d3blender.mock import new_scene, spawn

adapter, chart = new_scene('Chart')

data_v1 = [
    {'label': 'Jan', 'revenue': 12},
    {'label': 'Feb', 'revenue': 18},
    {'label': 'Mar', 'revenue': 9},
    {'label': 'Apr', 'revenue': 24},
]

x = scale_band([d['label'] for d in data_v1], range_=(0, 8), padding=0.2)
height = scale_linear(domain=(0, 24), range_=(0.2, 4.0))
FPS = 24


def bars():
    return select(adapter, '#Chart mesh').filter(lambda el: el.name.startswith('bar_'))


def enter_bar(d):
    el = spawn(adapter, chart, f"bar_{d['label']}")
    h = height(d['revenue'])
    el.location = (x(d['label']), 0, h / 2)
    el.scale = (x.bandwidth() / 2, 0.5, h / 2)
    el['revenue'] = d['revenue']
    return el


def update_bar(el, d):
    new_h = height(d['revenue'])
    sel = select(adapter, el)  # re-wrap the known element -- no CSS round trip
    sel.keyframe(1, location=el.location, scale=el.scale)                       # hold current pose
    sel.keyframe(FPS, location=(x(d['label']), 0, new_h / 2),
                 scale=(x.bandwidth() / 2, 0.5, new_h / 2))                     # animate to new height
    el['revenue'] = d['revenue']


def exit_bar(el):
    adapter.remove(el)


bars().data(data_v1, key=lambda i, d: d['label']).join(enter=enter_bar)

# Rerun with changed data: Feb's revenue changes, Apr is dropped entirely.
data_v2 = [
    {'label': 'Jan', 'revenue': 12},
    {'label': 'Feb', 'revenue': 30},
    {'label': 'Mar', 'revenue': 9},
]

result = bars().data(data_v2, key=lambda i, d: d['label']).join(
    enter=enter_bar, update=update_bar, exit=exit_bar)

if __name__ == '__main__':
    print("bars remaining:", sorted(el.name for el in result))
    result.each(lambda el, i: print(
        f"{el.name}: revenue={el['revenue']} keyframes={len(el._keyframes)}"))
