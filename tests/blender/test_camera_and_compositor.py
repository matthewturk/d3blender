"""Real-bpy confirmation that cameras and compositor nodes are already
fully reachable through the existing generic get_attr/set_attr
path-walker -- no adapter changes needed, the same story as material
shader inputs. See README's "Cameras" and "Compositor nodes" sections
and CLAUDE.md for the full writeup, including the real version-drift
gotcha the compositor case surfaced (scene.node_tree -> a real node
group datablock, scene.compositing_node_group, in this Blender
version)."""

import bpy

from d3blender import select
from d3blender.blender_adapter import get_adapter


def test_camera_is_a_selectable_object_like_any_other(spawn):
    chart = bpy.data.collections.new('Chart')
    bpy.context.scene.collection.children.link(chart)
    cam_data = bpy.data.cameras.new('Cam')
    cam_obj = bpy.data.objects.new('Camera', cam_data)
    chart.objects.link(cam_obj)

    adapter = get_adapter()
    result = select(adapter, 'camera')

    assert [el.name for el in result] == ['Camera']


def test_camera_object_transform_via_existing_attr():
    cam_obj = bpy.data.objects.new('Camera', bpy.data.cameras.new('Cam'))
    bpy.context.scene.collection.objects.link(cam_obj)
    adapter = get_adapter()

    adapter.set_attr(cam_obj, 'location', (5, -5, 3))

    assert tuple(cam_obj.location) == (5, -5, 3)


def test_camera_data_properties_via_existing_path_walker():
    cam_data = bpy.data.cameras.new('Cam')
    cam_obj = bpy.data.objects.new('Camera', cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    adapter = get_adapter()

    assert adapter.get_attr(cam_obj, ('data', 'lens')) == 50.0  # bpy's own default

    adapter.set_attr(cam_obj, ('data', 'lens'), 85.0)
    assert cam_data.lens == 85.0

    adapter.set_attr(cam_obj, ('data', 'clip_end'), 500.0)
    assert cam_data.clip_end == 500.0

    adapter.set_attr(cam_obj, ('data', 'dof', 'use_dof'), True)
    adapter.set_attr(cam_obj, ('data', 'dof', 'focus_distance'), 10.0)
    assert cam_data.dof.use_dof is True
    assert cam_data.dof.focus_distance == 10.0


def test_compositor_node_property_via_existing_path_walker():
    """Confirms the version-current compositor shape: a real node-group
    datablock on scene.compositing_node_group (not the older
    scene.node_tree), same modernized-interface pattern as materials
    and Geometry Nodes. A node's plain bpy_struct properties (not every
    input is a socket) are reachable the same way modifier properties
    always were."""
    scene = bpy.context.scene
    group = bpy.data.node_groups.new('Compositing', 'CompositorNodeTree')
    scene.compositing_node_group = group
    scene.use_nodes = True
    glare = group.nodes.new('CompositorNodeGlare')
    glare.name = 'Glare'

    adapter = get_adapter()
    path = ('compositing_node_group', 'nodes', 'Glare', 'inputs', 'Threshold', 'default_value')

    assert adapter.get_attr(scene, path) == 1.0  # bpy's own default
    adapter.set_attr(scene, path, 0.5)
    assert glare.inputs['Threshold'].default_value == 0.5
