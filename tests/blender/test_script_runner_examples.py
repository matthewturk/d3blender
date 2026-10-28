"""Runs examples/script_runner/*.py the way the Script Runner extension
does -- load the file as a module, call execute(context, params) with a
params dict built from PARAMS defaults (COLLECTION params unset = None)
-- including reruns and setting changes, to check they update in place
instead of duplicating. Script Runner itself isn't needed or imported."""

import importlib.util
import os

import bpy
import pytest

FOLDER = os.path.join(os.path.dirname(__file__), '..', '..', 'examples', 'script_runner')


def _load(name):
    spec = importlib.util.spec_from_file_location(f'd3_example_{name}', os.path.join(FOLDER, f'{name}.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _params(module, **overrides):
    values = {k: spec.get('default') for k, spec in module.PARAMS.items() if k != 'label'}
    values.update(overrides)
    return values


def _run(module, **overrides):
    assert module.execute(bpy.context, _params(module, **overrides)) == {'FINISHED'}


def _meshes_in(name):
    return [o for o in bpy.data.collections[name].objects]


def test_bar_chart_reruns_in_place_and_follows_settings():
    m = _load('bar_chart_csv')
    _run(m)
    bars = _meshes_in('Bar Chart')
    assert len(bars) == 12
    names = sorted(o.name for o in bars)
    tallest = max(bars, key=lambda o: o.scale[2])
    assert tallest['revenue'] == 30.8

    first_top = tallest.scale[2]
    _run(m, height=8.0)  # same nice() domain, twice the range: every bar doubles
    assert sorted(o.name for o in _meshes_in('Bar Chart')) == names
    assert max(o.scale[2] for o in _meshes_in('Bar Chart')) == pytest.approx(2 * first_top, rel=1e-5)

    _run(m, value='units')
    assert sorted(o.name for o in _meshes_in('Bar Chart')) == names
    assert all('units' in o for o in _meshes_in('Bar Chart'))
    assert len([o for o in bpy.data.objects if o.type == 'MESH']) == 12


def test_bar_chart_animation_toggles_cleanly():
    m = _load('bar_chart_csv')
    _run(m, animate=True, stagger=2)
    bars = sorted(_meshes_in('Bar Chart'), key=lambda o: o.location[0])
    assert all(o.animation_data and o.animation_data.action for o in bars)
    start = bpy.context.scene.frame_start
    bpy.context.scene.frame_set(start)
    assert bars[0].scale[2] == pytest.approx(1e-4, abs=1e-5)
    bpy.context.scene.frame_set(start + 2 * 11 + 20)
    assert all(o.scale[2] > 0.1 for o in bars)

    _run(m, animate=False)
    assert all(o.animation_data is None for o in _meshes_in('Bar Chart'))


def test_bar_chart_into_a_given_collection():
    m = _load('bar_chart_csv')
    target = bpy.data.collections.new('Mine')
    bpy.context.scene.collection.children.link(target)
    _run(m, target=target)
    assert len(target.objects) == 12
    assert 'Bar Chart' not in bpy.data.collections


def test_scatter_reruns_in_place_and_drops_removed_rows():
    m = _load('scatter_csv')
    _run(m)
    pts = _meshes_in('Scatter Plot')
    assert len(pts) == 60
    before = {o['d3_key']: tuple(o.location) for o in pts}

    _run(m, extent=12.0, radius=0.2)
    pts = _meshes_in('Scatter Plot')
    assert len(pts) == 60
    for o in pts:
        assert tuple(o.location) == pytest.approx(tuple(2 * c for c in before[o['d3_key']]), abs=1e-4)

    _run(m, size_by='', color_by='')
    assert len({tuple(round(c, 4) for c in o.color) for o in _meshes_in('Scatter Plot')}) == 1
    assert len({round(o.scale[0], 5) for o in _meshes_in('Scatter Plot')}) == 1


def test_csv_to_points_attributes_resize_and_cleanup(tmp_path):
    m = _load('csv_to_points')
    _run(m)
    obj = bpy.data.objects['CSV Points']
    mesh = obj.data
    assert len(mesh.vertices) == 2000
    assert mesh.attributes['temperature'].data_type == 'FLOAT'
    assert mesh.attributes['cluster'].data_type == 'INT'
    assert obj.modifiers['d3 Points'].node_group.name == 'd3 Points Display'

    _run(m, radius=0.1, fit=True, size=2.0)
    assert bpy.data.objects['CSV Points'] == obj
    xs = [v.co[0] for v in mesh.vertices]
    assert min(xs) == pytest.approx(-1.0, abs=1e-4) and max(xs) == pytest.approx(1.0, abs=1e-4)
    from d3blender.blender_adapter import get_adapter
    assert get_adapter().get_attr(obj, ('modifiers', 'd3 Points', 'Radius')) == pytest.approx(0.1)

    small = tmp_path / 'small.csv'
    small.write_text('x,y,z,flag\n0,0,0,true\n1,1,1,false\n2,2,2,true\n')
    _run(m, csv_path=str(small), spheres=False)
    assert len(mesh.vertices) == 3
    assert mesh.attributes['flag'].data_type == 'BOOLEAN'
    assert 'temperature' not in mesh.attributes  # columns gone from the CSV are cleaned up
    assert 'd3 Points' not in obj.modifiers
    assert len([o for o in bpy.data.objects if o.name.startswith('CSV Points')]) == 1
