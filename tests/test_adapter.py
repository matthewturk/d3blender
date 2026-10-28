from d3blender import select
from d3blender.adapter import SceneAdapter
from d3blender.mock import MockCollection, spawn


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


def test_create_line_mesh_is_a_single_object_with_one_edge_per_segment():
    adapter = SceneAdapter(objects=[], collections=[])
    chart = adapter.get_or_create_collection('Chart')
    segments = [((0, 0, 0), (1, 0, 0)), ((2, 0, 0), (3, 0, 0)), ((4, 0, 0), (5, 0, 0))]

    ticks = adapter.create_line_mesh(chart, 'ticks', segments)

    assert [el.name for el in select(adapter, '#Chart mesh')] == ['ticks']
    vertices, edges = ticks.mesh_data
    assert len(edges) == len(segments)
    assert len(vertices) == 2 * len(segments)


def test_create_line_mesh_does_not_double_count_via_objects_without_collection():
    adapter = SceneAdapter(objects=[], collections=[])
    chart = adapter.get_or_create_collection('Chart')
    adapter.create_line_mesh(chart, 'ticks', [((0, 0, 0), (1, 0, 0))])
    assert adapter.objects_without_collection() == []


# -- parent-scoped lookup ---------------------------------------------------

def test_get_or_create_collection_with_parent_only_looks_among_that_parents_children():
    adapter = SceneAdapter(objects=[], collections=[])
    root_a = adapter.get_or_create_collection('RootA')
    root_b = adapter.get_or_create_collection('RootB')

    halos_a = adapter.get_or_create_collection('Halos', parent=root_a)
    halos_b = adapter.get_or_create_collection('Halos', parent=root_b)

    assert halos_a is not halos_b
    assert root_a.children == [halos_a]
    assert root_b.children == [halos_b]


def test_get_or_create_collection_with_parent_is_idempotent_per_parent():
    adapter = SceneAdapter(objects=[], collections=[])
    root_a = adapter.get_or_create_collection('RootA')
    root_b = adapter.get_or_create_collection('RootB')
    halos_a = adapter.get_or_create_collection('Halos', parent=root_a)
    halos_b = adapter.get_or_create_collection('Halos', parent=root_b)

    assert adapter.get_or_create_collection('Halos', parent=root_a) is halos_a
    assert adapter.get_or_create_collection('Halos', parent=root_b) is halos_b
    assert len(adapter.collections) == 4


def test_get_or_create_collection_with_parent_finds_an_existing_unstamped_child():
    # A child built by hand (no d3_name stamp) is still found by exact name.
    root = MockCollection('Root')
    halos = MockCollection('Halos')
    root.children.append(halos)
    adapter = SceneAdapter(objects=[], collections=[root, halos])

    assert adapter.get_or_create_collection('Halos', parent=root) is halos


def test_get_or_create_collection_with_parent_finds_a_renamed_child_by_its_stamp():
    # Stands in for real Blender auto-suffixing a new child to "Halos.001"
    # because "Halos" was already taken elsewhere: the rerun must find it
    # through the d3_name stamp, not create a third one.
    adapter = SceneAdapter(objects=[], collections=[])
    root = adapter.get_or_create_collection('Root')
    halos = adapter.get_or_create_collection('Halos', parent=root)
    halos.name = 'Halos.001'

    assert adapter.get_or_create_collection('Halos', parent=root) is halos
    assert halos.get(SceneAdapter.COLLECTION_NAME_PROP) == 'Halos'


def test_get_or_create_collection_without_parent_still_looks_globally():
    # Backward compatibility: parent=None returns an existing nested
    # collection of that name rather than making a new top-level one.
    adapter = SceneAdapter(objects=[], collections=[])
    root = adapter.get_or_create_collection('Root')
    halos = adapter.get_or_create_collection('Halos', parent=root)

    assert adapter.get_or_create_collection('Halos') is halos


def test_get_or_create_collection_under_an_untracked_parent_stays_selectable():
    # The scene's root collection isn't in bpy.data.collections; nesting
    # under an untracked parent like it must not hide the new collection
    # from select().
    adapter = SceneAdapter(objects=[], collections=[])
    scene_root = MockCollection('Scene Collection')

    chart = adapter.get_or_create_collection('Chart', parent=scene_root)
    spawn(adapter, chart, 'bar_0')

    assert chart in scene_root.children
    assert chart in adapter.top_level_collections()
    assert [el.name for el in select(adapter, '#Chart mesh')] == ['bar_0']
