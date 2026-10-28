"""Real-bpy coverage for LiveBlenderAdapter.creator() and Join.join()'s
string shorthand -- the mock suite (tests/test_join_creator.py) only
covers the clear-refusal/dispatch-wiring side; this confirms real
primitive creation, per-datum creation kwargs, collection linking, and
the documented "shape params aren't settable after creation" wall."""

import bpy

from d3blender import select
from d3blender.blender_adapter import get_adapter


def test_creator_builds_a_real_uv_sphere_with_default_shape():
    adapter = get_adapter()
    chart = adapter.get_or_create_collection('Chart')

    make = adapter.creator('uv_sphere', chart)
    obj = make({'label': 'a'})

    assert obj.type == 'MESH'
    assert obj in list(chart.objects)
    assert len(obj.data.vertices) > 0
    assert len(obj.data.polygons) > 0


def test_creator_accepts_plain_creation_kwargs():
    adapter = get_adapter()
    chart = adapter.get_or_create_collection('Chart')

    small = adapter.creator('uv_sphere', chart, segments=8, ring_count=4)({'label': 'a'})
    big = adapter.creator('uv_sphere', chart, segments=32, ring_count=16)({'label': 'b'})

    assert len(small.data.vertices) < len(big.data.vertices)


def test_creator_accepts_per_datum_callable_kwargs():
    adapter = get_adapter()
    chart = adapter.get_or_create_collection('Chart')

    make = adapter.creator('uv_sphere', chart, radius=lambda d: d['radius'])
    small = make({'radius': 0.5})
    big = make({'radius': 2.0})

    # radius isn't a settable property afterward, but it IS baked into
    # the rest positions at creation time -- confirm the two differ.
    small_extent = max(abs(c) for v in small.data.vertices for c in v.co)
    big_extent = max(abs(c) for v in big.data.vertices for c in v.co)
    assert big_extent > small_extent


def test_creator_unknown_name_raises_clearly():
    adapter = get_adapter()
    chart = adapter.get_or_create_collection('Chart')
    try:
        adapter.creator('teapot', chart)
    except ValueError as exc:
        assert 'uv_sphere' in str(exc)  # names the available registry
    else:
        raise AssertionError('expected a ValueError for an unknown shape name')


def test_shape_params_are_not_settable_after_creation():
    """The wall this whole design works around, confirmed directly:
    segments/ring_count aren't real object or mesh properties, so
    nothing -- not even a plain attribute assignment -- can reshape an
    already-created sphere after the fact."""
    adapter = get_adapter()
    chart = adapter.get_or_create_collection('Chart')
    obj = adapter.creator('uv_sphere', chart, segments=8, ring_count=4)({})
    before = len(obj.data.vertices)

    assert not hasattr(obj, 'segments')
    assert not hasattr(obj.data, 'segments')
    obj['segments'] = 64  # a custom prop, not the real thing -- changes nothing
    assert len(obj.data.vertices) == before


def test_join_string_shorthand_end_to_end(spawn):
    adapter = get_adapter()
    chart = adapter.get_or_create_collection('Chart')
    data = [{'label': 'a', 'radius': 1.0}, {'label': 'b', 'radius': 2.0}]

    balls = (
        select(adapter, chart)
        .select('mesh')
        .data(data, key=lambda i, d: d['label'])
        .join('uv_sphere', collection=chart, radius=lambda d: d['radius'])
        .attr('location', lambda el, d, i: (i * 3, 0, 0))
    )

    assert len(balls.elements) == 2
    assert [tuple(el.location) for el in balls.elements] == [(0, 0, 0), (3, 0, 0)]
    assert all(el in list(chart.objects) for el in balls.elements)

    # rerun-safe: same key, same collection -- should match, not duplicate
    rebound = (
        select(adapter, chart)
        .select('mesh')
        .data(data, key=lambda i, d: d['label'])
        .join('uv_sphere', collection=chart, radius=lambda d: d['radius'])
    )
    assert len(rebound.elements) == 2
    assert {el.name for el in rebound.elements} == {el.name for el in balls.elements}


def test_join_creator_kwargs_scale_after_join_varies_apparent_size(spawn):
    """The documented correct alternative to per-datum shape kwargs:
    .attr('scale', ...) after a uniform-shape join, real and mutable."""
    adapter = get_adapter()
    chart = adapter.get_or_create_collection('Chart')
    data = [{'label': 'a', 'radius': 1.0}, {'label': 'b', 'radius': 3.0}]

    balls = (
        select(adapter, chart)
        .select('mesh')
        .data(data, key=lambda i, d: d['label'])
        .join('uv_sphere', collection=chart)
        .attr('scale', lambda el, d, i: (d['radius'],) * 3)
    )

    assert tuple(balls.elements[0].scale) == (1.0, 1.0, 1.0)
    assert tuple(balls.elements[1].scale) == (3.0, 3.0, 3.0)
