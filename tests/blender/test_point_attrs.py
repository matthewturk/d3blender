"""Real-bpy coverage for LiveBlenderAdapter's bulk point_attr/
set_point_attr override -- the mock suite (tests/test_point_attrs.py)
covers the generic per-item logic; this pins down the bulk
foreach_get/foreach_set path and the real mesh.attributes shapes it
depends on (verified against bpy 5.2: FLOAT/INT/BOOLEAN -> .value,
FLOAT_VECTOR -> .vector, FLOAT_COLOR -> .color)."""

import bpy

from d3blender.blender_adapter import get_adapter


def _ball(spawn):
    """A 3-vertex mesh object, real bpy geometry -- built via the `spawn`
    fixture (conftest.py) plus a manual from_pydata(), since `spawn`
    itself only makes an empty mesh datablock."""
    obj = spawn('Ball', bpy.context.scene.collection)
    obj.data.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [], [])
    obj.data.update()
    return obj


def test_point_count(spawn):
    obj = _ball(spawn)
    assert get_adapter().point_count(obj) == 3


def test_position_read_and_write_round_trip(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    assert adapter.point_attr(obj, 'position') == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    adapter.set_point_attr(obj, 'position', [(9, 9, 9), (8, 8, 8), (7, 7, 7)])
    assert adapter.point_attr(obj, 'position') == [(9, 9, 9), (8, 8, 8), (7, 7, 7)]
    assert [tuple(v.co) for v in obj.data.vertices] == [(9, 9, 9), (8, 8, 8), (7, 7, 7)]


def test_set_point_attr_refuses_a_length_mismatch(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    try:
        adapter.set_point_attr(obj, 'position', [(0, 0, 0), (1, 0, 0)])
    except ValueError as exc:
        assert 'never resizes' in str(exc)
    else:
        raise AssertionError('expected a length-mismatch ValueError')
    assert adapter.point_count(obj) == 3


def test_scalar_vector_and_color_attributes_round_trip(spawn):
    obj = _ball(spawn)
    adapter = get_adapter()

    adapter.set_point_attr(obj, 'revenue', [12.0, 18.0, 9.0])
    assert adapter.point_attr(obj, 'revenue') == [12.0, 18.0, 9.0]
    assert obj.data.attributes['revenue'].data_type == 'FLOAT'

    adapter.set_point_attr(obj, 'bucket', [1, 2, 3])
    assert adapter.point_attr(obj, 'bucket') == [1, 2, 3]
    assert obj.data.attributes['bucket'].data_type == 'INT'

    adapter.set_point_attr(obj, 'flag', [True, False, True])
    assert adapter.point_attr(obj, 'flag') == [True, False, True]
    assert obj.data.attributes['flag'].data_type == 'BOOLEAN'

    adapter.set_point_attr(obj, 'offset', [(1, 0, 0), (0, 1, 0), (0, 0, 1)])
    assert adapter.point_attr(obj, 'offset') == [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    assert obj.data.attributes['offset'].data_type == 'FLOAT_VECTOR'

    adapter.set_point_attr(obj, 'fill', [(1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1)])
    assert adapter.point_attr(obj, 'fill') == [
        (1.0, 0.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0)]
    assert obj.data.attributes['fill'].data_type == 'FLOAT_COLOR'


def test_bulk_and_generic_paths_agree(spawn):
    """The whole point of LiveBlenderAdapter overriding point_attr/
    set_point_attr is speed, not different behavior -- confirm the bulk
    (foreach_*) path and the inherited generic per-item loop
    (SceneAdapter's version, called directly) produce identical results
    against the same real mesh."""
    from d3blender.adapter import SceneAdapter

    obj = spawn('Ball', bpy.context.scene.collection)
    obj.data.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)], [], [])
    obj.data.update()

    bulk = get_adapter()
    generic = SceneAdapter(objects=[obj], collections=[])

    bulk.set_point_attr(obj, 'position', [(1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, 4)])
    assert generic.point_attr(obj, 'position') == bulk.point_attr(obj, 'position')

    generic.set_point_attr(obj, 'revenue', [1.0, 2.0, 3.0, 4.0])
    assert bulk.point_attr(obj, 'revenue') == generic.point_attr(obj, 'revenue')
