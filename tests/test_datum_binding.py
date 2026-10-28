"""Coverage for Selection.datum -- the parallel bound-data list Join.join()
populates, and the (el, i) / (el, d, i) / (el) arity dispatch in
_invoke() that lets .attr()/.each()/.keyframe()/.filter() callables use
whichever shape they want. See selection.py's module docstring and
_arity()'s docstring for why this exists (closing the gap with real
d3's own (d, i) => ... accessors)."""

from d3blender import select
from d3blender.mock import new_scene, spawn
from d3blender.selection import Selection


def _balls():
    adapter, chart = new_scene('Chart')
    data = [
        {'label': 'a', 'amplitude': 0.1},
        {'label': 'b', 'amplitude': 0.2},
    ]
    balls = (select(adapter, '#Chart mesh')
             .data(data, key=lambda i, d: d['label'])
             .join(enter=lambda d: spawn(adapter, chart, f"ball_{d['label']}")))
    return adapter, balls, data


def test_each_receives_the_bound_datum_in_order():
    adapter, balls, data = _balls()
    seen = []
    balls.each(lambda el, d, i: seen.append((el.name, d['label'], i)))
    assert seen == [('ball_a', 'a', 0), ('ball_b', 'b', 1)]


def test_each_two_arg_form_still_works():
    adapter, balls, data = _balls()
    seen = []
    balls.each(lambda el, i: seen.append((el.name, i)))
    assert seen == [('ball_a', 0), ('ball_b', 1)]


def test_attr_accessor_can_use_the_bound_datum():
    adapter, balls, data = _balls()
    balls.attr('amplitude', lambda el, d, i: d['amplitude'])
    assert adapter.get_attr(balls.elements[0], 'amplitude') == 0.1
    assert adapter.get_attr(balls.elements[1], 'amplitude') == 0.2


def test_attr_two_arg_accessor_still_works():
    adapter, balls, data = _balls()
    balls.attr('amplitude', lambda el, i: data[i]['amplitude'])
    assert adapter.get_attr(balls.elements[0], 'amplitude') == 0.1
    assert adapter.get_attr(balls.elements[1], 'amplitude') == 0.2


def test_keyframe_accessor_can_use_the_bound_datum():
    # 'location' rather than a custom prop like 'amplitude' -- mock.py's
    # keyframe_insert reads the current value via plain getattr(), which
    # only works for real attributes, not custom properties; a
    # pre-existing gap unrelated to datum binding, not something this
    # test should paper over by picking a key that dodges it.
    adapter, balls, data = _balls()
    balls.keyframe(5, location=lambda el, d, i: (d['amplitude'] * 10, 0, 0))
    assert adapter.get_attr(balls.elements[0], 'location') == (1.0, 0, 0)
    assert adapter.get_attr(balls.elements[1], 'location') == (2.0, 0, 0)
    assert balls.elements[0]._keyframes[-1][1] == 'location'


def test_filter_predicate_one_arg_still_works():
    adapter, balls, data = _balls()
    kept = balls.filter(lambda el: el.name == 'ball_a')
    assert [el.name for el in kept.elements] == ['ball_a']


def test_filter_predicate_can_use_the_bound_datum():
    adapter, balls, data = _balls()
    kept = balls.filter(lambda el, d, i: d['amplitude'] > 0.15)
    assert [el.name for el in kept.elements] == ['ball_b']


def test_filter_propagates_datum_for_surviving_elements():
    adapter, balls, data = _balls()
    kept = balls.filter(lambda el, d, i: d['label'] == 'b')
    assert kept.datum == [{'label': 'b', 'amplitude': 0.2}]


def test_filter_by_selector_string_also_propagates_datum():
    adapter, balls, data = _balls()
    kept = balls.filter('#ball_b')
    assert kept.datum == [{'label': 'b', 'amplitude': 0.2}]


def test_rerunning_join_updates_the_bound_datum_not_stale_data():
    adapter, chart = new_scene('Chart')
    data = [{'label': 'a', 'amplitude': 0.1}, {'label': 'b', 'amplitude': 0.2}]
    (select(adapter, '#Chart mesh')
        .data(data, key=lambda i, d: d['label'])
        .join(enter=lambda d: spawn(adapter, chart, f"ball_{d['label']}")))

    updated_data = [{'label': 'a', 'amplitude': 0.9}, {'label': 'b', 'amplitude': 0.2}]

    def enter_should_not_run(d):
        raise AssertionError(f'unexpected enter for {d!r} -- both keys already exist')

    rebound = (select(adapter, '#Chart mesh')
               .data(updated_data, key=lambda i, d: d['label'])
               .join(enter=enter_should_not_run, update=lambda el, d: None))

    assert rebound.datum[0]['amplitude'] == 0.9


def test_plain_selector_query_has_unbound_datum():
    adapter, balls, data = _balls()
    result = select(adapter, '#Chart mesh')
    assert result.datum == [None, None]
    # a 3-arg callback still works fine against unbound data -- just gets None
    seen = []
    result.each(lambda el, d, i: seen.append(d))
    assert seen == [None, None]


def test_scoped_select_returns_unbound_datum_even_from_a_bound_selection(scene):
    weapons = select(scene, '#Weapons')
    bound = weapons.data([{'note': 'weapons collection'}], key=lambda i, d: 'weapons').join(
        enter=lambda d: weapons.elements[0], update=lambda el, d: None)
    assert bound.datum == [{'note': 'weapons collection'}]

    # .select() finds real descendants (Sword, Shield) -- but there's no
    # 1:1 parent-datum-to-child mapping, so the result comes back unbound.
    descendants = bound.select('.enemy')
    assert sorted(el.name for el in descendants.elements) == ['Shield', 'Sword']
    assert descendants.datum == [None, None]


def test_direct_selection_construction_without_datum_defaults_to_none():
    adapter, chart = new_scene('Chart')
    obj = spawn(adapter, chart, 'Solo')
    sel = Selection(adapter, [obj])
    assert sel.datum == [None]


def test_remove_still_returns_an_empty_selection():
    adapter, balls, data = _balls()
    empty = balls.remove()
    assert empty.elements == []
    assert empty.datum == []
