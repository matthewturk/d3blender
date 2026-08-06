"""Everything in tests/ (the mock suite) already covers SceneAdapter's
generic logic. These tests are narrower on purpose: they exercise real
bpy, so they only need to check the things that could plausibly differ
against a live scene -- LiveBlenderAdapter's own overrides, and the
duck-typed reads/writes in adapter.py that have never run against real
bpy shapes before (see CLAUDE.md's Testing status section)."""

import bpy

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
