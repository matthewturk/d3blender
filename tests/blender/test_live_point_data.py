"""Real-bpy coverage for blender_adapter.live_point_data() -- the
frame_change_pre-driven wiring on top of points.point_data(). Nothing
here is mock-testable: bpy.app.handlers doesn't exist without real bpy,
by definition."""

import bpy

from d3blender.blender_adapter import get_adapter, live_point_data


def _ball(spawn, name='Ball'):
    obj = spawn(name, bpy.context.scene.collection)
    obj.data.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [], [])
    obj.data.update()
    return obj


def test_applies_immediately_at_the_current_frame(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    stop = live_point_data(adapter, obj, position=lambda frame: [(frame, 0, 0)] * 3)
    try:
        assert adapter.point_attr(obj, 'position')[0] == (bpy.context.scene.frame_current, 0, 0)
    finally:
        stop()


def test_recomputes_on_frame_change(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    stop = live_point_data(adapter, obj, position=lambda frame: [(frame, 0, 0)] * 3)
    try:
        bpy.context.scene.frame_set(7)
        assert adapter.point_attr(obj, 'position')[0] == (7, 0, 0)
        bpy.context.scene.frame_set(13)
        assert adapter.point_attr(obj, 'position')[0] == (13, 0, 0)
    finally:
        stop()


def test_rebinding_the_same_object_replaces_rather_than_stacking(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    stop1 = live_point_data(adapter, obj, position=lambda frame: [(frame, 0, 0)] * 3)
    before = len(bpy.app.handlers.frame_change_pre)
    stop2 = live_point_data(adapter, obj, position=lambda frame: [(frame, 0, 0)] * 3)
    after = len(bpy.app.handlers.frame_change_pre)

    try:
        assert after == before  # no net growth -- the old handler was replaced, not stacked
        bpy.context.scene.frame_set(20)
        assert adapter.point_attr(obj, 'position')[0] == (20, 0, 0)
    finally:
        stop2()


def test_stop_removes_the_handler_and_freezes_the_last_value(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    stop = live_point_data(adapter, obj, position=lambda frame: [(frame, 0, 0)] * 3)
    bpy.context.scene.frame_set(20)
    assert adapter.point_attr(obj, 'position')[0] == (20, 0, 0)

    stop()
    bpy.context.scene.frame_set(99)
    assert adapter.point_attr(obj, 'position')[0] == (20, 0, 0)  # unchanged -- handler is gone


def test_two_objects_are_bound_independently(spawn):
    a = _ball(spawn, 'A')
    b = _ball(spawn, 'B')
    adapter = get_adapter()

    stop_a = live_point_data(adapter, a, position=lambda frame: [(frame, 0, 0)] * 3)
    stop_b = live_point_data(adapter, b, position=lambda frame: [(frame * 10, 0, 0)] * 3)
    try:
        bpy.context.scene.frame_set(3)
        assert adapter.point_attr(a, 'position')[0] == (3, 0, 0)
        assert adapter.point_attr(b, 'position')[0] == (30, 0, 0)
    finally:
        stop_a()
        stop_b()
    assert len(bpy.app.handlers.frame_change_pre) == 0
