from d3blender import select
from d3blender.adapter import SceneAdapter
from d3blender.mock import (
    MockCollection,
    MockGNInputValue,
    MockModifier,
    MockNodeGroup,
    MockNodeGroupInterfaceItem,
    MockObject,
)


def _scatter_object():
    node_group = MockNodeGroup([
        MockNodeGroupInterfaceItem('Size', 'Input_2'),
        MockNodeGroupInterfaceItem('Density', 'Input_3'),
        MockNodeGroupInterfaceItem('Geometry', 'Input_0', in_out='OUTPUT'),
    ])
    gn = MockModifier('NODES', name='Scatter', node_group=node_group)
    gn.properties.inputs['Input_2'] = MockGNInputValue(1.0)
    gn.properties.inputs['Input_3'] = MockGNInputValue(10)

    chart = MockCollection('Chart')
    obj = MockObject('Emitter', 'MESH')
    obj.modifiers.append(gn)
    obj.users_collection = (chart,)
    chart.objects.append(obj)

    adapter = SceneAdapter(objects=[obj], collections=[chart])
    return adapter, obj


def test_get_attr_reads_gn_input_by_name_tuple_form():
    adapter, obj = _scatter_object()
    assert adapter.get_attr(obj, ('modifiers', 'Scatter', 'Size')) == 1.0


def test_get_attr_reads_gn_input_by_name_string_form():
    adapter, obj = _scatter_object()
    assert adapter.get_attr(obj, 'modifiers.Scatter.Density') == 10


def test_output_socket_is_not_treated_as_an_input():
    adapter, obj = _scatter_object()
    assert adapter.get_attr(obj, ('modifiers', 'Scatter', 'Geometry')) is None


def test_set_attr_writes_gn_input_by_name():
    adapter, obj = _scatter_object()
    adapter.set_attr(obj, ('modifiers', 'Scatter', 'Size'), 3.5)
    assert adapter.get_attr(obj, ('modifiers', 'Scatter', 'Size')) == 3.5


def test_selection_attr_setter_accepts_a_tuple_key():
    adapter, obj = _scatter_object()
    select(adapter, '#Emitter').attr(('modifiers', 'Scatter', 'Density'), 42)
    assert adapter.get_attr(obj, ('modifiers', 'Scatter', 'Density')) == 42


def test_dotted_modifier_name_requires_tuple_form():
    node_group = MockNodeGroup([MockNodeGroupInterfaceItem('Size', 'Input_2')])
    gn = MockModifier('NODES', name='Scatter.001', node_group=node_group)
    gn.properties.inputs['Input_2'] = MockGNInputValue(1.0)
    obj = MockObject('Emitter2', 'MESH')
    obj.modifiers.append(gn)
    adapter = SceneAdapter(objects=[obj], collections=[])

    # String form mis-splits "Scatter.001" into two path segments.
    assert adapter.get_attr(obj, 'modifiers.Scatter.001.Size') is None
    # Tuple form treats "Scatter.001" as one segment -- correct.
    assert adapter.get_attr(obj, ('modifiers', 'Scatter.001', 'Size')) == 1.0


def test_gn_inputs_lists_named_inputs_only():
    adapter, obj = _scatter_object()
    gn = obj.modifiers[0]
    assert adapter.gn_inputs(gn) == {'Size': 1.0, 'Density': 10}


def test_plain_modifier_property_gettable_and_settable_via_dotted_path():
    obj = MockObject('Cube', 'MESH')
    bevel = MockModifier('BEVEL', name='Bevel')
    obj.modifiers.append(bevel)
    adapter = SceneAdapter(objects=[obj], collections=[])

    adapter.set_attr(obj, 'modifiers.Bevel.width', 0.3)
    assert adapter.get_attr(obj, 'modifiers.Bevel.width') == 0.3
