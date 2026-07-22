from d3blender import select
from d3blender.adapter import SceneAdapter
from d3blender.mock import MockCollection, MockMaterial, MockMaterialSlot, MockObject


def _scene():
    chart = MockCollection('Chart')

    red = MockObject('Red', 'MESH')
    red.active_material = MockMaterial('Enemy_Red')
    red.material_slots = [MockMaterialSlot(MockMaterial('Enemy_Red'))]

    # Multi-slot: active material is Ally_Blue, but Enemy_Red is also
    # present in a second slot -- only :has-material() should see it.
    blue = MockObject('Blue', 'MESH')
    blue.active_material = MockMaterial('Ally_Blue')
    blue.material_slots = [
        MockMaterialSlot(MockMaterial('Ally_Blue')),
        MockMaterialSlot(MockMaterial('Enemy_Red')),
    ]

    plain = MockObject('Plain', 'MESH')

    for obj in (red, blue, plain):
        obj.users_collection = (chart,)
        chart.objects.append(obj)

    return SceneAdapter(objects=[red, blue, plain], collections=[chart])


def test_material_attribute_equality_sees_only_the_active_material():
    adapter = _scene()
    assert [el.name for el in select(adapter, '[material=Enemy_Red]')] == ['Red']


def test_material_attribute_existence():
    adapter = _scene()
    assert sorted(el.name for el in select(adapter, '[material]')) == ['Blue', 'Red']


def test_has_material_pseudo_checks_every_slot():
    adapter = _scene()
    assert sorted(el.name for el in select(adapter, ':has-material(Enemy_Red)')) == ['Blue', 'Red']


def test_object_without_material_is_excluded_from_both_forms():
    adapter = _scene()
    assert 'Plain' not in [el.name for el in select(adapter, '[material]')]
    assert 'Plain' not in [el.name for el in select(adapter, ':has-material(Enemy_Red)')]
