"""Real-bpy confirmation that cameras and compositor nodes are already
fully reachable through the existing generic get_attr/set_attr
path-walker -- no adapter changes needed, the same story as material
shader inputs. See README's "Cameras" and "Compositor nodes" sections
and CLAUDE.md for the full writeup, including the real version-drift
gotcha the compositor case surfaced twice (scene.node_tree -> a real
node group datablock on scene.compositing_node_group in 5.2, then
scene.compositor_effects[...].node_group in 5.4, with the 5.2 properties
deprecated)."""

import bpy
import pytest

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


def _new_compositor_group(scene):
    """Attach a fresh CompositorNodeTree to `scene` the version-current
    way, returning (group, path_prefix) -- the path-walker prefix that
    reaches the group from `scene`.

    - Where it exists (present on 5.4.0 Alpha, absent on the 5.2 wheel;
      5.3 not checked): `scene.compositor_effects`, a
      collection of SceneCompositorEffect, each with its own `node_group`.
      `scene.compositing_node_group`/`scene.use_nodes` still exist there
      but are deprecated (removal expected in 6.0);
      `compositing_node_group` is a shim for the active effect's group.
    - Otherwise (the 5.2 wheel): no `compositor_effects`; the group goes
      straight on `scene.compositing_node_group` plus `use_nodes = True`.
    """
    group = bpy.data.node_groups.new('Compositing', 'CompositorNodeTree')
    if hasattr(scene, 'compositor_effects'):
        effect = scene.compositor_effects.new('FX')
        effect.node_group = group
        return group, ('compositor_effects', 'FX', 'node_group')
    scene.compositing_node_group = group
    scene.use_nodes = True
    return group, ('compositing_node_group',)


def test_compositor_node_property_via_existing_path_walker():
    """Confirms the version-current compositor shape (see
    _new_compositor_group) is reachable with no adapter changes, same
    modernized-interface pattern as materials and Geometry Nodes. With
    compositor_effects, the 'FX' segment resolves through the effects collection's `.get(name)`
    (the path-walker's second fallback; plain getattr misses it)."""
    scene = bpy.context.scene
    group, prefix = _new_compositor_group(scene)
    glare = group.nodes.new('CompositorNodeGlare')
    glare.name = 'Glare'

    adapter = get_adapter()
    path = prefix + ('nodes', 'Glare', 'inputs', 'Threshold', 'default_value')

    assert adapter.get_attr(scene, path) == 1.0  # bpy's own default
    adapter.set_attr(scene, path, 0.5)
    assert glare.inputs['Threshold'].default_value == 0.5


# bl_rna, not hasattr(bpy.types.Scene, ...): RNA properties aren't class
# attributes, so a class-level hasattr is False even where they exist.
@pytest.mark.skipif('compositor_effects' not in bpy.types.Scene.bl_rna.properties,
                    reason='no scene.compositor_effects in this Blender (absent on 5.2, present on 5.4)')
def test_compositor_effect_settings_reachable_by_effect_name():
    scene = bpy.context.scene
    _new_compositor_group(scene)
    adapter = get_adapter()

    adapter.set_attr(scene, ('compositor_effects', 'FX', 'enable_for_render'), False)

    assert scene.compositor_effects.get('FX').enable_for_render is False
    assert adapter.get_attr(scene, ('compositor_effects', 'FX', 'enable_for_render')) is False
