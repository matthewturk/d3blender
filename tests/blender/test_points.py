"""Real-bpy coverage for points.point_data() -- the mock suite
(tests/test_points.py) covers the orchestration logic itself; this
confirms it drives real per-vertex writes correctly, and specifically
that recomputing over many frames stays cheap and leaves no animation
data behind (see CLAUDE.md's design notes for why that matters: this is
the option we settled on over per-vertex F-curve keyframing)."""

import bpy

from d3blender.blender_adapter import get_adapter
from d3blender.points import point_data


def _ball(spawn):
    obj = spawn('Ball', bpy.context.scene.collection)
    obj.data.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [], [])
    obj.data.update()
    return obj


def test_point_data_writes_real_vertex_positions(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    point_data(adapter, obj, 5, position=lambda frame: [(frame, 0, 0)] * 3)

    assert [tuple(v.co) for v in obj.data.vertices] == [(5, 0, 0)] * 3


def test_point_data_across_many_frames_leaves_no_animation_data(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    for frame in range(1, 61):
        point_data(adapter, obj, frame, position=lambda f: [(f, 0, 0)] * 3)

    assert [tuple(v.co) for v in obj.data.vertices] == [(60, 0, 0)] * 3
    assert obj.data.animation_data is None


def test_point_data_multiple_channels_against_real_mesh(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    point_data(adapter, obj, 3,
               position=lambda frame: [(frame, i, 0) for i in range(3)],
               revenue=lambda frame: [float(frame)] * 3)

    assert [tuple(v.co) for v in obj.data.vertices] == [(3, 0, 0), (3, 1, 0), (3, 2, 0)]
    assert obj.data.attributes['revenue'].data_type == 'FLOAT'
    assert [d.value for d in obj.data.attributes['revenue'].data] == [3.0, 3.0, 3.0]
