import pytest

from d3blender.adapter import SceneAdapter
from d3blender.mock import MockCollection, spawn_points
from d3blender.points import point_data


def _ball():
    collection = MockCollection('Chart')
    adapter = SceneAdapter(objects=[], collections=[collection])
    obj = spawn_points(adapter, collection, 'Ball',
                        vertices=[(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    return adapter, obj


def test_point_data_writes_a_channel_computed_from_frame():
    adapter, obj = _ball()
    point_data(adapter, obj, 5, position=lambda frame: [(frame, 0, 0)] * 3)
    assert adapter.point_attr(obj, 'position') == [(5, 0, 0)] * 3


def test_point_data_recomputes_from_scratch_each_call_no_state_kept():
    adapter, obj = _ball()
    point_data(adapter, obj, 1, position=lambda frame: [(frame, 0, 0)] * 3)
    point_data(adapter, obj, 2, position=lambda frame: [(frame, 0, 0)] * 3)
    assert adapter.point_attr(obj, 'position') == [(2, 0, 0)] * 3


def test_point_data_writes_multiple_channels_in_one_call():
    adapter, obj = _ball()
    point_data(adapter, obj, 3,
               position=lambda frame: [(frame, 0, 0)] * 3,
               revenue=lambda frame: [float(frame)] * 3)
    assert adapter.point_attr(obj, 'position') == [(3, 0, 0)] * 3
    assert adapter.point_attr(obj, 'revenue') == [3.0, 3.0, 3.0]


def test_point_data_channel_can_be_a_per_vertex_formula():
    adapter, obj = _ball()
    point_data(adapter, obj, 10,
               position=lambda frame: [(frame + i, 0, 0) for i in range(3)])
    assert adapter.point_attr(obj, 'position') == [(10, 0, 0), (11, 0, 0), (12, 0, 0)]


def test_point_data_channel_can_manage_its_own_state_via_closure():
    # The "explicit transition, caller manages it" case: the closure
    # holds its own lookup table and point_data() never needs to know.
    states = {0: [(0, 0, 0)] * 3, 10: [(5, 5, 5)] * 3}

    def looked_up(frame):
        return states[frame]

    adapter, obj = _ball()
    point_data(adapter, obj, 0, position=looked_up)
    assert adapter.point_attr(obj, 'position') == [(0, 0, 0)] * 3
    point_data(adapter, obj, 10, position=looked_up)
    assert adapter.point_attr(obj, 'position') == [(5, 5, 5)] * 3


def test_point_data_still_refuses_a_length_mismatch():
    adapter, obj = _ball()
    with pytest.raises(ValueError, match='never resizes'):
        point_data(adapter, obj, 1, position=lambda frame: [(0, 0, 0)] * 2)


def test_point_data_returns_the_element_for_chaining():
    adapter, obj = _ball()
    result = point_data(adapter, obj, 1, position=lambda frame: [(0, 0, 0)] * 3)
    assert result is obj
