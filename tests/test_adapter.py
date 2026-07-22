from d3blender import select
from d3blender.adapter import SceneAdapter
from d3blender.mock import spawn


def test_get_or_create_collection_makes_a_top_level_collection():
    adapter = SceneAdapter(objects=[], collections=[])
    chart = adapter.get_or_create_collection('Chart')
    assert chart.name == 'Chart'
    assert chart in adapter.top_level_collections()
    assert [c.name for c in select(adapter, '#Chart')] == ['Chart']


def test_get_or_create_collection_is_idempotent():
    adapter = SceneAdapter(objects=[], collections=[])
    first = adapter.get_or_create_collection('Chart')
    second = adapter.get_or_create_collection('Chart')
    assert first is second
    assert len(adapter.collections) == 1


def test_get_or_create_collection_with_parent_nests_and_is_not_top_level():
    adapter = SceneAdapter(objects=[], collections=[])
    root = adapter.get_or_create_collection('Root')
    child = adapter.get_or_create_collection('Child', parent=root)
    assert child not in adapter.top_level_collections()
    assert [c.name for c in select(adapter, '#Root > collection')] == ['Child']


def test_spawned_object_is_queryable_under_a_newly_created_collection():
    adapter = SceneAdapter(objects=[], collections=[])
    chart = adapter.get_or_create_collection('Chart')
    spawn(adapter, chart, 'bar_0')
    assert [el.name for el in select(adapter, '#Chart mesh')] == ['bar_0']
