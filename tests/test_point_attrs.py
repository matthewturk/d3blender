import pytest

from d3blender.adapter import SceneAdapter
from d3blender.mock import MockCollection, spawn_points


def _ball():
    collection = MockCollection('Chart')
    adapter = SceneAdapter(objects=[], collections=[collection])
    obj = spawn_points(adapter, collection, 'Ball',
                        vertices=[(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    return adapter, obj


def test_point_count():
    adapter, obj = _ball()
    assert adapter.point_count(obj) == 3


def test_point_count_is_zero_for_a_non_mesh_object():
    from d3blender.mock import MockObject
    adapter = SceneAdapter(objects=[], collections=[])
    empty = MockObject('Empty', 'EMPTY')
    assert adapter.point_count(empty) == 0


def test_position_read_reflects_initial_vertices():
    adapter, obj = _ball()
    assert adapter.point_attr(obj, 'position') == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]


def test_position_write_updates_every_vertex():
    adapter, obj = _ball()
    adapter.set_point_attr(obj, 'position', [(9, 9, 9), (8, 8, 8), (7, 7, 7)])
    assert adapter.point_attr(obj, 'position') == [(9, 9, 9), (8, 8, 8), (7, 7, 7)]
    assert [v.co for v in obj.data.vertices] == [(9, 9, 9), (8, 8, 8), (7, 7, 7)]


def test_set_point_attr_refuses_a_length_mismatch_rather_than_resizing():
    adapter, obj = _ball()
    with pytest.raises(ValueError, match='never resizes'):
        adapter.set_point_attr(obj, 'position', [(0, 0, 0), (1, 0, 0)])  # 2, not 3
    # and the mesh is untouched -- refusal, not a partial write
    assert adapter.point_count(obj) == 3


def test_scalar_attribute_created_on_first_write_and_typed_as_float():
    adapter, obj = _ball()
    adapter.set_point_attr(obj, 'revenue', [12.0, 18.0, 9.0])
    assert adapter.point_attr(obj, 'revenue') == [12.0, 18.0, 9.0]
    assert obj.data.attributes['revenue'].data_type == 'FLOAT'


def test_int_attribute_inferred_from_int_sample():
    adapter, obj = _ball()
    adapter.set_point_attr(obj, 'bucket', [1, 2, 3])
    assert adapter.point_attr(obj, 'bucket') == [1, 2, 3]
    assert obj.data.attributes['bucket'].data_type == 'INT'


def test_bool_attribute_inferred_from_bool_sample_not_int():
    adapter, obj = _ball()
    adapter.set_point_attr(obj, 'flag', [True, False, True])
    assert adapter.point_attr(obj, 'flag') == [True, False, True]
    assert obj.data.attributes['flag'].data_type == 'BOOLEAN'


def test_vector_attribute_inferred_from_3tuple():
    adapter, obj = _ball()
    adapter.set_point_attr(obj, 'offset', [(1, 0, 0), (0, 1, 0), (0, 0, 1)])
    assert adapter.point_attr(obj, 'offset') == [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    assert obj.data.attributes['offset'].data_type == 'FLOAT_VECTOR'


def test_color_attribute_inferred_from_4tuple():
    adapter, obj = _ball()
    adapter.set_point_attr(obj, 'fill', [(1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1)])
    assert adapter.point_attr(obj, 'fill') == [(1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1)]
    assert obj.data.attributes['fill'].data_type == 'FLOAT_COLOR'


def test_writing_an_existing_attribute_again_keeps_its_established_type():
    adapter, obj = _ball()
    adapter.set_point_attr(obj, 'revenue', [1.0, 2.0, 3.0])
    adapter.set_point_attr(obj, 'revenue', [4.0, 5.0, 6.0])
    assert adapter.point_attr(obj, 'revenue') == [4.0, 5.0, 6.0]
    assert len(obj.data.attributes) == 1


def test_reading_a_nonexistent_attribute_is_a_keyerror():
    adapter, obj = _ball()
    with pytest.raises(KeyError):
        adapter.point_attr(obj, 'nope')


def test_set_point_attr_length_mismatch_on_a_custom_attribute_also_refuses():
    adapter, obj = _ball()
    with pytest.raises(ValueError, match='never resizes'):
        adapter.set_point_attr(obj, 'revenue', [1.0, 2.0])
