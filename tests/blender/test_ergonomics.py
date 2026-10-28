"""Real-bpy coverage for the ergonomics layer: no-adapter select(), the
d3.collection()/select_all()/join('cube') flow and its rerun behaviour,
parent-linking of a bare bpy.data.objects.new() result, and
transition()'s keyframes."""

import bpy
from bpy_extras import anim_utils

import d3blender as d3


def _keys(obj, data_path, index=0):
    bag = anim_utils.action_get_channelbag_for_slot(
        obj.animation_data.action, obj.animation_data.action_slot)
    fc = next(f for f in bag.fcurves if f.data_path == data_path and f.array_index == index)
    return [tuple(kp.co) for kp in fc.keyframe_points]


def test_select_without_an_adapter_sees_the_live_scene(spawn):
    chart = d3.collection('Chart')
    spawn('Bar', chart, d3_class='bar')

    assert [el.name for el in d3.select('.bar')] == ['Bar']
    # A fresh snapshot per call: an object added afterwards shows up next time.
    spawn('Bar2', chart, d3_class='bar')
    assert sorted(el.name for el in d3.select('.bar')) == ['Bar', 'Bar2']


def test_select_all_join_shape_reruns_in_place():
    chart = d3.collection('Chart')
    rows = [{'label': 'a', 'v': 1.0}, {'label': 'b', 'v': 2.0}]

    def run(rows, height):
        return (d3.select_all(chart)
                .data(rows, key='label')
                .join('cube', size=1.0)
                .attr('scale', lambda el, d, i: (1, 1, d['v'] * height)))

    first = run(rows, 1.0)
    assert len(chart.objects) == 2
    second = run(rows, 3.0)
    assert len(chart.objects) == 2
    assert [o.name for o in second] == [o.name for o in first]
    assert [tuple(o.scale)[2] for o in second] == [3.0, 6.0]

    run(rows[:1], 1.0)
    assert len(chart.objects) == 1
    assert len([o for o in bpy.data.objects if o.type == 'MESH']) == 1


def test_bare_new_object_from_enter_is_linked_into_the_parent():
    chart = d3.collection('Chart')
    sel = d3.select_all(chart).data(['x'], key=lambda d: d).join(
        lambda d: bpy.data.objects.new(f'Empty_{d}', None))

    obj = sel.elements[0]
    assert list(obj.users_collection) == [chart]
    assert obj['d3_key'] == 'x'
    # And a rerun finds it rather than making another.
    again = d3.select_all(chart).data(['x'], key=lambda d: d).join(
        lambda d: bpy.data.objects.new('Unexpected', None))
    assert again.elements == [obj]
    assert 'Unexpected' not in bpy.data.objects


def test_transition_writes_start_and_end_keys_per_element():
    chart = d3.collection('Chart')
    bpy.context.scene.frame_set(5)
    sel = d3.select_all(chart).data([0, 1], key=lambda d: d).join(
        lambda d: bpy.data.objects.new(f'E{d}', None))

    sel.transition(10, delay=lambda el, i: i * 4).attr('location', lambda el, d, i: (d + 1.0, 0.0, 0.0))

    assert _keys(sel.elements[0], 'location') == [(5.0, 0.0), (15.0, 1.0)]
    assert _keys(sel.elements[1], 'location') == [(9.0, 0.0), (19.0, 2.0)]
