import datetime

from d3blender import (
    select,
    scale_linear,
    scale_band,
    scale_ordinal,
    scale_time,
    scale_sequential,
    interpolate_rgb,
)
from d3blender.mock import MockObject


def test_scale_linear():
    height = scale_linear(domain=(0, 24), range_=(0.2, 4.0))
    assert height(0) == 0.2
    assert height(24) == 4.0
    assert round(height(12), 4) == round((0.2 + 4.0) / 2, 4)


def test_scale_band_spacing_and_bandwidth():
    x = scale_band(['Jan', 'Feb', 'Mar', 'Apr'], range_=(0, 8), padding=0.2)
    assert x('Jan') < x('Feb') < x('Mar') < x('Apr')
    assert 0 < x.bandwidth() < x.step


def test_scale_ordinal_cycles():
    color = scale_ordinal(['a', 'b'], range_=['red', 'blue'])
    assert color('a') == 'red'
    assert color('b') == 'blue'


def test_scale_time_maps_dates_onto_a_numeric_range():
    jan1 = datetime.datetime(2026, 1, 1)
    dec31 = datetime.datetime(2026, 12, 31)
    x = scale_time((jan1, dec31), range_=(0, 10))
    assert x(jan1) == 0
    assert round(x(dec31), 4) == 10
    midyear = datetime.datetime(2026, 7, 2, 12)  # ~ the midpoint of the year
    assert 4.5 < x(midyear) < 5.5


def test_scale_time_invert_returns_a_datetime():
    jan1 = datetime.datetime(2026, 1, 1)
    dec31 = datetime.datetime(2026, 12, 31)
    x = scale_time((jan1, dec31), range_=(0, 10))
    inverted = x.invert(0)
    assert isinstance(inverted, datetime.datetime)
    assert inverted == jan1


def test_scale_time_accepts_plain_dates_too():
    jan1 = datetime.date(2026, 1, 1)
    dec31 = datetime.date(2026, 12, 31)
    x = scale_time((jan1, dec31), range_=(0, 10))
    assert x(jan1) == 0
    assert round(x(dec31), 4) == 10


def test_scale_sequential_maps_domain_through_interpolator():
    heat = scale_sequential((0, 100), interpolator=lambda t: t)
    assert heat(0) == 0
    assert heat(100) == 1
    assert heat(50) == 0.5


def test_scale_sequential_clamps_out_of_domain_input():
    heat = scale_sequential((0, 100), interpolator=lambda t: t)
    assert heat(-50) == 0
    assert heat(500) == 1


def test_interpolate_rgb_lerps_between_two_colors():
    fade = interpolate_rgb((0, 0, 0), (255, 255, 255))
    assert fade(0) == (0, 0, 0)
    assert fade(1) == (255, 255, 255)
    assert fade(0.5) == (127.5, 127.5, 127.5)


def test_interpolate_rgb_handles_rgba():
    fade = interpolate_rgb((1.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 0.5))
    assert fade(0) == (1.0, 0.0, 0.0, 1.0)
    assert fade(1) == (0.0, 0.0, 1.0, 0.5)


def test_scale_sequential_with_interpolate_rgb_end_to_end():
    color = scale_sequential((0, 24), interpolator=interpolate_rgb((0, 0, 0), (1, 1, 1)))
    assert color(0) == (0.0, 0.0, 0.0)
    assert color(24) == (1.0, 1.0, 1.0)
    assert color(12) == (0.5, 0.5, 0.5)


def test_keyframe_records_value_and_frame(scene):
    props = next(c for c in scene.collections if c.name == 'Props')
    box = MockObject('Box', 'MESH')
    props.objects.append(box)
    box.users_collection = (props,)
    scene.objects.append(box)

    sel = select(scene, '#Box')
    sel.keyframe(1, location=(0, 0, 0))
    sel.keyframe(25, location=(4, 0, 0))

    assert box._keyframes == [
        (1, 'location', (0, 0, 0)),
        (25, 'location', (4, 0, 0)),
    ]
