"""Everything in tests/ (the mock suite) already covers SceneAdapter's
generic logic. These tests are narrower on purpose: they exercise real
bpy, so they only need to check the things that could plausibly differ
against a live scene -- LiveBlenderAdapter's own overrides, and the
duck-typed reads/writes in adapter.py that have never run against real
bpy shapes before (see CLAUDE.md's Testing status section)."""

import bpy
import pytest
from bpy_extras import anim_utils

from d3blender import select
from d3blender.blender_adapter import get_adapter


def test_get_adapter_wraps_the_real_scene(spawn):
    coll = bpy.data.collections.new('Weapons')
    bpy.context.scene.collection.children.link(coll)
    spawn('Sword', coll, hp=30)

    adapter = get_adapter()

    assert any(adapter.name_of(o) == 'Sword' for o in adapter.objects)
    assert any(adapter.name_of(c) == 'Weapons' for c in adapter.collections)


def test_select_query_against_real_objects_and_custom_properties(spawn):
    coll = bpy.data.collections.new('Weapons')
    bpy.context.scene.collection.children.link(coll)
    spawn('Sword', coll, hp=30, d3_class='enemy')
    spawn('Shield', coll, hp=40, d3_class='enemy')
    spawn('Barrel', coll, hp=5)

    adapter = get_adapter()
    result = select(adapter, '.enemy[hp>30]')

    assert [el.name for el in result] == ['Shield']


def test_remove_deletes_the_object_datablock(spawn):
    coll = bpy.data.collections.new('Weapons')
    bpy.context.scene.collection.children.link(coll)
    sword = spawn('Sword', coll)

    adapter = get_adapter()
    adapter.remove(sword)

    assert 'Sword' not in bpy.data.objects


def test_remove_deletes_a_collection_datablock():
    coll = bpy.data.collections.new('Weapons')
    bpy.context.scene.collection.children.link(coll)

    adapter = get_adapter()
    adapter.remove(coll)

    assert 'Weapons' not in bpy.data.collections


def test_get_or_create_collection_creates_and_links_a_real_collection():
    adapter = get_adapter()

    coll = adapter.get_or_create_collection('Chart')

    assert coll.name == 'Chart'
    assert coll in list(bpy.context.scene.collection.children)


def test_get_or_create_collection_is_idempotent():
    adapter = get_adapter()

    first = adapter.get_or_create_collection('Chart')
    second = adapter.get_or_create_collection('Chart')

    assert first is second
    assert len(bpy.data.collections) == 1


def test_get_or_create_collection_nests_under_a_parent():
    adapter = get_adapter()
    parent = adapter.get_or_create_collection('Chart')

    child = adapter.get_or_create_collection('Bars', parent=parent)

    assert child in list(parent.children)
    assert child not in list(bpy.context.scene.collection.children)


def test_create_line_mesh_builds_a_real_mesh_with_one_edge_per_segment():
    adapter = get_adapter()
    coll = adapter.get_or_create_collection('Axis')
    segments = [((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (2, 0, 0))]

    obj = adapter.create_line_mesh(coll, 'Ticks', segments)

    assert obj.name == 'Ticks'
    assert obj.type == 'MESH'
    assert len(obj.data.vertices) == 4
    assert len(obj.data.edges) == 2
    assert obj in list(coll.objects)


def test_get_or_create_collection_scopes_lookup_to_the_parent_and_suffixes_names():
    """Two roots each get their own "Halos" child. Real collection names
    are global, so the second one is auto-suffixed by Blender itself --
    expected; the d3_name stamp is what lets a rerun find it again."""
    adapter = get_adapter()
    root_a = adapter.get_or_create_collection('RootA')
    root_b = adapter.get_or_create_collection('RootB')

    halos_a = adapter.get_or_create_collection('Halos', parent=root_a)
    halos_b = adapter.get_or_create_collection('Halos', parent=root_b)

    assert halos_a != halos_b
    assert halos_a.name == 'Halos'
    assert halos_b.name == 'Halos.001'
    assert list(root_a.children) == [halos_a]
    assert list(root_b.children) == [halos_b]

    # Rerun, with a fresh adapter as a real script rerun would have.
    adapter = get_adapter()
    assert adapter.get_or_create_collection('Halos', parent=root_a) == halos_a
    assert adapter.get_or_create_collection('Halos', parent=root_b) == halos_b
    assert len(bpy.data.collections) == 4


def test_get_or_create_collection_under_the_scene_root_stays_selectable(spawn):
    """parent=bpy.context.scene.collection (an untracked collection) used
    to drop the new collection out of select()'s reach entirely."""
    adapter = get_adapter()

    chart = adapter.get_or_create_collection('Chart', parent=bpy.context.scene.collection)
    spawn('Bar', chart)

    assert chart in list(bpy.context.scene.collection.children)
    assert [el.name for el in select(adapter, '#Chart mesh')] == ['Bar']
    assert [el.name for el in select(get_adapter(), '#Chart mesh')] == ['Bar']


def test_keyframe_with_a_per_element_frame_accessor_writes_real_fcurve_keys(spawn):
    adapter = get_adapter()
    chart = adapter.get_or_create_collection('Chart')
    data = [{'id': 'a', 'frame': 7, 'x': 1.0}, {'id': 'b', 'frame': 19, 'x': 2.0}]

    sel = (select(adapter, '#Chart mesh')
           .data(data, key=lambda i, d: d['id'])
           .join(enter=lambda d: spawn(f"Ball_{d['id']}", chart)))
    sel.keyframe(lambda el, d, i: d['frame'], location=lambda el, d, i: (d['x'], 0.0, 0.0))

    # Layered actions (Blender 5.x, confirmed on bpy 5.2): Action.fcurves
    # is gone, F-curves live in the slot's channelbag.
    for el, d in zip(sel.elements, data):
        bag = anim_utils.action_get_channelbag_for_slot(
            el.animation_data.action, el.animation_data.action_slot)
        fcurve_x = next(fc for fc in bag.fcurves
                        if fc.data_path == 'location' and fc.array_index == 0)
        keys = [tuple(kp.co) for kp in fcurve_x.keyframe_points]
        assert keys == [(d['frame'], d['x'])]


def test_keyframe_on_a_custom_property_writes_an_id_property_fcurve(spawn):
    """bpy's own keyframe_insert('hp') raises 'property "hp" not found'
    for a custom prop (confirmed on 5.2 and 5.4); the adapter retries
    with the ID-property path '["hp"]'."""
    chart = get_adapter().get_or_create_collection('Chart')
    obj = spawn('Ball', chart, hp=1.0)
    adapter = get_adapter()

    select(adapter, obj).keyframe(3, hp=5.0).keyframe(9, hp=7.0)

    bag = anim_utils.action_get_channelbag_for_slot(
        obj.animation_data.action, obj.animation_data.action_slot)
    fcurve = next(fc for fc in bag.fcurves if fc.data_path == '["hp"]')
    assert [tuple(kp.co) for kp in fcurve.keyframe_points] == [(3.0, 5.0), (9.0, 7.0)]
    bpy.context.scene.frame_set(6)
    assert obj['hp'] == pytest.approx(6.0, abs=0.01)  # symmetric midpoint of the F-curve
