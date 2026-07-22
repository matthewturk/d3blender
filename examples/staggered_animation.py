"""
Boxes moving across a scaled region, staggered like d3's
.transition().delay(i => i * 5). Blender already has a real tweening
engine (F-curves), so .keyframe() just sets values and drops a keyframe
at a frame -- no interpolation to fake ourselves.
Run: python examples/staggered_animation.py
"""

from d3blender import select, scale_linear
from d3blender.adapter import SceneAdapter
from d3blender.mock import MockObject, MockCollection

chart = MockCollection('Chart')
adapter = SceneAdapter(objects=[], collections=[chart])


def add_cube(name):
    o = MockObject(name, 'MESH')
    chart.objects.append(o)
    o.users_collection = (chart,)
    adapter.objects.append(o)
    return o


items = [{'id': i} for i in range(5)]
region = scale_linear(domain=(0, len(items) - 1), range_=(-4, 4))  # the "scaled region"

boxes = (select(adapter, '#Chart mesh')
         .data(items, key=lambda i, d: f"anim_{d['id']}")
         .join(enter=lambda d: add_cube(f"anim_{d['id']}")))

FPS = 24
for i, (el, d) in enumerate(zip(boxes.elements, items)):
    start_frame = 1 + i * 5        # the "delay"
    end_frame = start_frame + FPS  # one-second move, per box

    sel = select(adapter, f'#{el.name}')
    sel.keyframe(start_frame, location=(region(0), i * 1.2, 0))
    sel.keyframe(end_frame, location=(region(len(items) - 1), i * 1.2, 0))

if __name__ == '__main__':
    for el in boxes.elements:
        print(f"{el.name} keyframes: {el._keyframes}")
