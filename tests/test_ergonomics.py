"""The ergonomics layer: adapter-less select(), select_all(collection) as a
join's starting point, .data() key shorthands, join() defaults to the
selection's parent, .entered/.updated, and transitions. Plus one test
that pins the exact call shape existing callers use (blender-config's
halo/geo/gpx importers), so backward compatibility is tested, not assumed."""

import importlib.util

import pytest

import d3blender as d3
from d3blender import select, select_all
from d3blender.adapter import SceneAdapter
from d3blender.mock import MockObject, new_scene, spawn


@pytest.fixture
def default_mock():
    adapter, chart = new_scene('Chart')
    previous = d3.set_default_adapter(adapter)
    yield adapter, chart
    d3.set_default_adapter(previous)


# -- backward compatibility -------------------------------------------------

def test_existing_callers_call_shape_still_works():
    # select(adapter, list_of_objects).data(items, key=lambda i, d: ...)
    #   .join(enter, exit=...) and then .elements / .datum
    adapter, chart = new_scene('Chart')
    items = [('a', 1), ('b', 2)]
    removed = []

    def run(items):
        return select(adapter, list(chart.objects)).data(
            items, key=lambda i, d: d[0]
        ).join(lambda d: spawn(adapter, chart, f'obj_{d[0]}'), exit=removed.append)

    first = run(items)
    assert [el.name for el in first.elements] == ['obj_a', 'obj_b']
    assert first.datum == items

    second = run([('b', 3)])
    assert [el.name for el in second.elements] == ['obj_b']
    assert second.datum == [('b', 3)]
    assert [el.name for el in removed] == ['obj_a']


def test_select_keyword_form_still_works():
    adapter, chart = new_scene('Chart')
    spawn(adapter, chart, 'bar')
    assert [el.name for el in select(adapter=adapter, target='#Chart mesh')] == ['bar']


# -- adapter-less select ------------------------------------------------------

def test_select_without_adapter_uses_the_default(default_mock):
    adapter, chart = default_mock
    spawn(adapter, chart, 'bar')

    assert [el.name for el in select('#Chart mesh')] == ['bar']
    assert select('#Chart mesh').adapter is adapter
    assert [el.name for el in select(list(chart.objects))] == ['bar']
    assert [el.name for el in select('#Chart mesh', adapter=adapter)] == ['bar']


def test_default_adapter_factory_is_called_per_select():
    calls = []

    def factory():
        calls.append(1)
        return new_scene('Chart')[0]

    previous = d3.set_default_adapter(factory)
    try:
        select('mesh')
        select('mesh')
    finally:
        d3.set_default_adapter(previous)
    assert len(calls) == 2


@pytest.mark.skipif(importlib.util.find_spec('bpy') is not None,
                    reason='bpy is importable here, so the live default adapter works')
def test_select_without_adapter_outside_blender_explains_itself():
    previous = d3.set_default_adapter(None)
    try:
        with pytest.raises(RuntimeError, match='pass one explicitly'):
            select('mesh')
    finally:
        d3.set_default_adapter(previous)


def test_collection_helper_gets_or_creates(default_mock):
    adapter, chart = default_mock
    assert d3.collection('Chart') is chart
    bars = d3.collection('Bars', parent=chart)
    assert bars in chart.children
    assert d3.collection('Bars', parent=chart) is bars


# -- select_all + join ----------------------------------------------------------

def test_select_all_collection_remembers_its_parent_and_links_entered_objects(default_mock):
    adapter, chart = default_mock
    rows = [{'label': 'a', 'v': 1}, {'label': 'b', 'v': 2}]

    def run(rows):
        # enter returns an object that isn't in any collection yet
        return select_all(chart).data(rows, key='label').join(
            lambda d: MockObject(f"bar_{d['label']}"))

    first = run(rows)
    assert first.parent is chart
    assert [o.name for o in chart.objects] == ['bar_a', 'bar_b']
    assert all(o.users_collection == (chart,) for o in chart.objects)

    second = run(rows)  # rerun updates in place, no duplicates
    assert [o.name for o in chart.objects] == ['bar_a', 'bar_b']
    assert second.elements == first.elements


def test_join_does_not_relink_an_element_enter_already_placed(default_mock):
    adapter, chart = default_mock
    other = d3.collection('Elsewhere')
    sel = select_all(chart).data([1], key=lambda d: d).join(lambda d: spawn(adapter, other, 'x'))
    assert sel.elements[0].users_collection == (other,)
    assert list(chart.objects) == []


def test_join_shape_name_defaults_to_the_parent_collection():
    seen = []

    class RecordingAdapter(SceneAdapter):
        def creator(self, name, collection, **kw):
            seen.append((name, collection, kw))
            return lambda d: spawn(self, collection, f'{name}_{d}')

    chart = d3.collection('Chart', adapter=RecordingAdapter([], []))
    adapter = RecordingAdapter([], [chart])
    sel = select_all(chart, adapter=adapter).data([1, 2], key=lambda d: d).join('cube', size=2)

    assert seen == [('cube', chart, {'size': 2})]
    assert [el.name for el in sel] == ['cube_1', 'cube_2']


def test_join_shape_name_without_parent_still_needs_collection():
    adapter, chart = new_scene('Chart')
    with pytest.raises(TypeError):
        select(adapter, []).data([1]).join('cube')


def test_data_key_forms():
    adapter, chart = new_scene('Chart')
    rows = [{'id': 'x'}, {'id': 'y'}]
    by_field = select_all(chart, adapter=adapter).data(rows, key='id').join(
        lambda d: spawn(adapter, chart, d['id']))
    assert [adapter.get_attr(el, 'd3_key') for el in by_field] == ['x', 'y']

    by_one_arg = select_all(chart, adapter=adapter).data(rows, key=lambda d: d['id']).join(
        lambda d: spawn(adapter, chart, 'dup'))
    assert by_one_arg.elements == by_field.elements  # same keys -> same objects, nothing new


def test_join_result_is_the_merged_selection_with_entered_and_updated():
    adapter, chart = new_scene('Chart')
    make = lambda d: spawn(adapter, chart, f'o{d}')  # noqa: E731
    select_all(chart, adapter=adapter).data([1, 2], key=lambda d: d).join(make)

    sel = (select_all(chart, adapter=adapter)
           .data([2, 3], key=lambda d: d)
           .join(make)
           .attr('value', lambda el, d, i: d * 10))

    assert [el.name for el in sel] == ['o2', 'o3']
    assert [adapter.get_attr(el, 'value') for el in sel] == [20, 30]
    assert [el.name for el in sel.entered] == ['o3']
    assert sel.entered.datum == [3]
    assert [el.name for el in sel.updated] == ['o2']
    assert sel.updated.datum == [2]


def test_select_all_selector_narrows_to_one_group():
    adapter, chart = new_scene('Chart')
    bars = select_all(chart, adapter=adapter).data(['a'], key=lambda d: d).join(
        lambda d: spawn(adapter, chart, 'bar_a')).classed('bar', True)
    labels = select_all(chart, '.label', adapter=adapter).data(['a'], key=lambda d: d).join(
        lambda d: spawn(adapter, chart, 'label_a')).classed('label', True)

    # Rejoining the labels must not treat the bar (same key, other group) as its own.
    again = select_all(chart, '.label', adapter=adapter).data(['a'], key=lambda d: d).join(
        lambda d: spawn(adapter, chart, 'unexpected'))
    assert again.elements == labels.elements
    assert bars.elements[0] in chart.objects


# -- transitions ----------------------------------------------------------------

def _boxes(n=3):
    adapter, chart = new_scene('Chart')
    sel = select_all(chart, adapter=adapter).data(list(range(n)), key=lambda d: d).join(
        lambda d: spawn(adapter, chart, f'box{d}'))
    return adapter, sel


def test_transition_keyframes_current_then_target():
    adapter, sel = _boxes(1)
    adapter.frame_current = 10

    sel.transition(20).attr('location', (1, 2, 3))

    assert sel.elements[0]._keyframes == [
        (10, 'location', (0.0, 0.0, 0.0)),
        (30, 'location', (1, 2, 3)),
    ]


def test_transition_staggered_delay_and_explicit_start():
    adapter, sel = _boxes(3)

    sel.transition(10, delay=lambda el, i: i * 5, start=100).attr('location', lambda el, d, i: (d, 0, 0))

    assert [[k[0] for k in el._keyframes] for el in sel] == [[100, 110], [105, 115], [110, 120]]
    assert [el._keyframes[-1][2] for el in sel] == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]


def test_chained_transition_starts_where_the_previous_ends():
    adapter, sel = _boxes(2)

    (sel.transition(10, delay=lambda el, i: i, start=1)
        .attr('location', (1, 0, 0))
        .transition(5)
        .attr('location', (2, 0, 0)))

    assert [k[0] for k in sel.elements[0]._keyframes] == [1, 11, 11, 16]
    assert [k[0] for k in sel.elements[1]._keyframes] == [2, 12, 12, 17]
    assert sel.elements[0]._keyframes[2][2] == (1, 0, 0)  # second leg starts from the first's end value


def test_transition_duration_and_delay_setters_chain():
    adapter, sel = _boxes(1)
    t = sel.transition(start=0).duration(4).delay(2)
    assert t.duration() == 4 and t.delay() == 2
    t.attr('location', (5, 0, 0))
    assert [k[0] for k in sel.elements[0]._keyframes] == [2, 6]
    assert t.selection() is sel


def test_transition_on_a_new_custom_property_only_writes_the_end_key():
    adapter, sel = _boxes(1)
    sel.transition(10, start=0).attr('hp', 5)
    assert sel.elements[0]._keyframes == [(10, '["hp"]', 5)]

    sel.transition(10, start=10).attr('hp', 9)  # now it exists: from 5 to 9
    assert sel.elements[0]._keyframes[1:] == [(10, '["hp"]', 5), (20, '["hp"]', 9)]
