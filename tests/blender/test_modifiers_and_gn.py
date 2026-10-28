"""The reason this whole tests/blender/ suite exists: the mock's
MockModifier/MockNodeGroup shapes are a best-effort mirror of real bpy,
but the actual bug that prompted this directory (`modifier[identifier] =
value` raising "id properties not supported for this type" on Blender
5.2+, see adapter.py's _gn_input_get/_gn_input_set) only ever showed up
against real bpy -- the mock happily accepted the old, now-wrong shape.
These tests pin the fix down against the real thing."""

import bpy
import pytest

from d3blender import select
from d3blender.blender_adapter import get_adapter


def _new_geometry_nodes_modifier(obj, group_name='Scatter'):
    group = bpy.data.node_groups.new(group_name, 'GeometryNodeTree')
    group.interface.new_socket(name='Size', in_out='INPUT', socket_type='NodeSocketFloat')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    mod = obj.modifiers.new(name=group_name, type='NODES')
    mod.node_group = group
    return mod


def test_plain_modifier_property_gettable_and_settable(spawn):
    obj = spawn('Cube', bpy.context.scene.collection)
    obj.modifiers.new(name='Bevel', type='BEVEL')
    adapter = get_adapter()

    adapter.set_attr(obj, 'modifiers.Bevel.width', 0.3)

    # Real bpy floats are single-precision, so 0.3 round-trips as
    # 0.30000001192092896 -- approx, not ==, same as any other
    # float32-backed RNA property.
    assert adapter.get_attr(obj, 'modifiers.Bevel.width') == pytest.approx(0.3)
    assert obj.modifiers['Bevel'].width == pytest.approx(0.3)


def test_geometry_nodes_input_gettable_and_settable_by_human_name(spawn):
    obj = spawn('Emitter', bpy.context.scene.collection)
    _new_geometry_nodes_modifier(obj)
    adapter = get_adapter()

    # Default value before any write, read straight through the path-walker.
    assert adapter.get_attr(obj, ('modifiers', 'Scatter', 'Size')) == 0.0

    adapter.set_attr(obj, ('modifiers', 'Scatter', 'Size'), 3.5)

    assert adapter.get_attr(obj, ('modifiers', 'Scatter', 'Size')) == 3.5
    # And confirm it actually landed in the real modifier, not just
    # something the adapter itself made up.
    identifier = next(
        item.identifier
        for item in obj.modifiers['Scatter'].node_group.interface.items_tree
        if item.name == 'Size'
    )
    assert obj.modifiers['Scatter'].properties.inputs[identifier]['value'] == 3.5


def test_geometry_nodes_input_identifier_is_not_the_pre_5_2_shape(spawn):
    """Documents the exact regression this suite exists to catch: real
    bpy 5.2+ identifiers are "Socket_N", and the value lives under
    `.properties.inputs[identifier]["value"]` (an IDPropertyGroup), not
    a direct `modifier[identifier]` ID property."""
    obj = spawn('Emitter', bpy.context.scene.collection)
    mod = _new_geometry_nodes_modifier(obj)

    identifier = next(
        item.identifier
        for item in mod.node_group.interface.items_tree
        if item.name == 'Size'
    )

    assert identifier.startswith('Socket_')
    try:
        mod[identifier] = 1.0
    except TypeError as exc:
        assert 'id properties not supported for this type' in str(exc)
    else:
        raise AssertionError(
            'modifier[identifier] = value no longer raises on this bpy '
            'version -- the pre-5.2 shape may be back, or this pinned '
            'bpy version moved again; re-check adapter.py\'s '
            '_gn_input_get/_gn_input_set against the new shape.'
        )


def test_gn_inputs_lists_named_inputs_only(spawn):
    obj = spawn('Emitter', bpy.context.scene.collection)
    mod = _new_geometry_nodes_modifier(obj)
    adapter = get_adapter()

    adapter.set_attr(obj, ('modifiers', 'Scatter', 'Size'), 2.0)

    assert adapter.gn_inputs(mod) == {'Size': 2.0}


def test_selection_attr_setter_reaches_a_real_gn_input(spawn):
    # A real, `bpy.data.collections`-tracked collection, not the scene's
    # own root ("Scene Collection") -- select() walks adapter.collections
    # to build its doc, and that root collection deliberately isn't in
    # `bpy.data.collections` at all (see get_adapter()), so an object
    # linked only there is invisible to any selector query. Not a bug
    # exercised here: get_or_create_collection() (the documented, only
    # supported way to make a join's root container) always produces a
    # real tracked collection, so idiomatic d3blender usage never hits
    # this gap -- see CLAUDE.md's Testing status section.
    chart = bpy.data.collections.new('Chart')
    bpy.context.scene.collection.children.link(chart)
    obj = spawn('Emitter', chart, d3_class='chart')
    _new_geometry_nodes_modifier(obj)
    adapter = get_adapter()

    select(adapter, '.chart').attr(('modifiers', 'Scatter', 'Size'), 4.0)

    assert adapter.get_attr(obj, ('modifiers', 'Scatter', 'Size')) == 4.0


def _socket_identifier(mod, name):
    return next(item.identifier for item in mod.node_group.interface.items_tree
                if item.name == name)


@pytest.mark.parametrize('socket_type, make_value, as_comparable', [
    ('NodeSocketFloat', lambda: 1.25, lambda v: v),
    ('NodeSocketInt', lambda: 7, lambda v: v),
    ('NodeSocketBool', lambda: True, lambda v: bool(v)),
    ('NodeSocketVector', lambda: (1.0, 2.0, 3.0), lambda v: tuple(v)),
    ('NodeSocketObject', lambda: bpy.data.objects.new('Target', None), lambda v: v),
    ('NodeSocketMaterial', lambda: bpy.data.materials.new('Mat'), lambda v: v),
], ids=['float', 'int', 'bool', 'vector', 'object', 'material'])
def test_geometry_nodes_input_round_trips_per_socket_type(spawn, socket_type, make_value,
                                                          as_comparable):
    """Pins the `properties.inputs[identifier]["value"]` storage shape per
    socket type, not just for floats -- ID-typed sockets (object,
    material) are the ones most likely to diverge. Run against the PyPI
    bpy 5.2 wheel by the normal suite, and against the real Blender 5.4
    application via run_in_blender_app.py (see this directory's README)."""
    obj = spawn('Emitter', bpy.context.scene.collection)
    group = bpy.data.node_groups.new('Group', 'GeometryNodeTree')
    group.interface.new_socket(name='Param', in_out='INPUT', socket_type=socket_type)
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    mod = obj.modifiers.new(name='GN', type='NODES')
    mod.node_group = group
    adapter = get_adapter()
    value = make_value()

    adapter.set_attr(obj, ('modifiers', 'GN', 'Param'), value)

    holder = mod.properties.inputs[_socket_identifier(mod, 'Param')]
    assert set(holder.keys()) >= {'value'}
    assert as_comparable(holder['value']) == value
    assert as_comparable(adapter.get_attr(obj, ('modifiers', 'GN', 'Param'))) == value
    assert as_comparable(adapter.gn_inputs(mod)['Param']) == value
