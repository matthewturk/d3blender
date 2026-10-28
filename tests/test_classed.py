"""Coverage for Selection.classed() -- d3's selection.classed(),
toggling one or more classes in the existing d3_class custom property
that .foo-style selectors already read (see classes_of())."""

from d3blender import select
from d3blender.mock import MockCollection, MockObject
from d3blender.adapter import SceneAdapter


def _scene_with(d3_class=''):
    obj = MockObject('Ball', 'MESH', d3_class=d3_class)
    coll = MockCollection('Chart')
    coll.objects.append(obj)
    obj.users_collection = (coll,)
    adapter = SceneAdapter(objects=[obj], collections=[coll])
    return adapter, obj


def test_classed_getter_false_when_absent():
    adapter, obj = _scene_with(d3_class='enemy')
    sel = select(adapter, '#Ball')
    assert sel.classed('boss') is False


def test_classed_getter_true_when_present():
    adapter, obj = _scene_with(d3_class='enemy boss')
    sel = select(adapter, '#Ball')
    assert sel.classed('boss') is True


def test_classed_getter_requires_all_named_classes():
    adapter, obj = _scene_with(d3_class='enemy')
    sel = select(adapter, '#Ball')
    assert sel.classed('enemy boss') is False  # has 'enemy' but not 'boss'


def test_classed_getter_on_empty_selection_is_false():
    adapter, obj = _scene_with()
    empty = select(adapter, '#NoSuchThing')
    assert empty.classed('anything') is False


def test_classed_setter_true_adds_without_disturbing_existing_classes():
    adapter, obj = _scene_with(d3_class='enemy')
    select(adapter, '#Ball').classed('boss', True)
    assert adapter.classes_of(obj) == {'enemy', 'boss'}


def test_classed_setter_false_removes_only_the_named_class():
    adapter, obj = _scene_with(d3_class='enemy boss')
    select(adapter, '#Ball').classed('boss', False)
    assert adapter.classes_of(obj) == {'enemy'}


def test_classed_setter_accepts_space_separated_multiple_names():
    adapter, obj = _scene_with(d3_class='')
    select(adapter, '#Ball').classed('enemy boss', True)
    assert adapter.classes_of(obj) == {'enemy', 'boss'}


def test_classed_setter_accepts_a_callable_with_datum():
    from d3blender.mock import new_scene, spawn
    adapter, chart = new_scene('Chart')
    data = [{'label': 'a', 'boss': True}, {'label': 'b', 'boss': False}]
    balls = (select(adapter, '#Chart mesh')
             .data(data, key=lambda i, d: d['label'])
             .join(enter=lambda d: spawn(adapter, chart, f"ball_{d['label']}", d3_class='enemy')))

    balls.classed('boss', lambda el, d, i: d['boss'])

    assert adapter.classes_of(balls.elements[0]) == {'enemy', 'boss'}
    assert adapter.classes_of(balls.elements[1]) == {'enemy'}


def test_classed_setter_two_arg_callable_still_works():
    from d3blender.mock import new_scene, spawn
    adapter, chart = new_scene('Chart')
    obj = spawn(adapter, chart, 'Ball', d3_class='enemy')
    select(adapter, '#Ball').classed('boss', lambda el, i: True)
    assert adapter.classes_of(obj) == {'enemy', 'boss'}


def test_classed_returns_self_for_chaining():
    adapter, obj = _scene_with(d3_class='enemy')
    result = select(adapter, '#Ball').classed('boss', True)
    assert result.elements == [obj]
