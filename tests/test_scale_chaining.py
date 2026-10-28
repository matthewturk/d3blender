"""d3-style chaining on every scale, alongside the original call form
(covered in test_scale_and_animation.py, which must keep passing)."""

import datetime
import math

import pytest

from d3blender import (
    scale_band,
    scale_linear,
    scale_ordinal,
    scale_sequential,
    scale_time,
    interpolate_rgb,
    ticks,
)


def test_linear_chained_equals_call_form():
    a = scale_linear((0, 24), (0.2, 4.0))
    b = scale_linear().domain((0, 24)).range((0.2, 4.0))
    assert [a(x) for x in (0, 6, 24)] == [b(x) for x in (0, 6, 24)]
    assert b.domain() == [0, 24] and b.range() == [0.2, 4.0]


def test_linear_nice_and_ticks():
    s = scale_linear().domain((0.2, 97.3)).nice()
    assert s.domain() == [0, 100]
    assert s.ticks(5) == [0, 20, 40, 60, 80, 100]
    assert scale_linear().domain((0, 1)).ticks(10) == [i / 10 for i in range(11)]
    assert scale_linear().domain((0.01, 0.98)).nice().domain() == [0.0, 1.0]


def test_ticks_function_matches_d3():
    assert ticks(0, 10, 5) == [0, 2, 4, 6, 8, 10]
    assert ticks(-1, 1, 4) == [-1.0, -0.5, 0.0, 0.5, 1.0]
    assert ticks(10, 0, 5) == [10, 8, 6, 4, 2, 0]
    assert ticks(3, 3) == [3]
    assert repr(ticks(0, 1, 10)[3]) == '0.3'


def test_linear_clamp_and_invert():
    s = scale_linear().domain((0, 10)).range((0, 100))
    assert s(20) == 200
    assert s.clamp()(20) == 100
    assert s.clamp(False)(20) == 200
    assert s.invert(50) == 5
    assert s.clamp().invert(500) == 10


def test_linear_interpolates_tuple_ranges():
    color = scale_linear().domain((0, 10)).range(((0, 0, 0, 1), (1, 0.5, 0, 1)))
    assert color(5) == (0.5, 0.25, 0.0, 1.0)


def test_copy_is_independent():
    a = scale_linear().domain((0, 10))
    b = a.copy().domain((0, 20))
    assert a.domain() == [0, 10] and b.domain() == [0, 20]


def test_time_chained_and_inverts_to_datetime():
    jan1, jan11 = datetime.datetime(2026, 1, 1), datetime.datetime(2026, 1, 11)
    s = scale_time().domain((jan1, jan11)).range((0, 10))
    assert s(datetime.datetime(2026, 1, 6)) == pytest.approx(5)
    assert s.invert(5) == datetime.datetime(2026, 1, 6)
    assert not hasattr(s, 'ticks')


def test_sequential_forms_and_clamp_default():
    gray = interpolate_rgb((0, 0, 0), (1, 1, 1))
    s1 = scale_sequential((0, 10), gray)
    s2 = scale_sequential(gray).domain((0, 10))
    s3 = scale_sequential().domain((0, 10)).interpolator(gray)
    assert s1(5) == s2(5) == s3(5) == (0.5, 0.5, 0.5)
    assert s1(20) == (1, 1, 1)                       # clamped by default
    assert s1.clamp(False)(20) == (2, 2, 2)


def test_band_chained_equals_call_form():
    a = scale_band(['a', 'b', 'c'], range_=(0, 9), padding=0.2)
    b = scale_band().domain(['a', 'b', 'c']).range((0, 9)).padding(0.2)
    assert [a(x) for x in 'abc'] == [b(x) for x in 'abc']
    assert a.bandwidth() == b.bandwidth()
    assert a.step == b.step == 3
    with pytest.raises(KeyError):
        b('z')


def test_ordinal_explicit_domain_keeps_original_unknown_behaviour():
    s = scale_ordinal(['a', 'b'], range_=['red', 'blue'])
    assert s('zzz') == 'red'
    assert s.unknown('gray')('zzz') == 'gray'


def test_ordinal_implicit_domain_grows_in_order_of_use():
    s = scale_ordinal().range(['red', 'blue'])
    assert [s(x) for x in ('x', 'y', 'z', 'x')] == ['red', 'blue', 'red', 'red']
    assert s.domain() == ['x', 'y', 'z']


def test_nan_safe_nice_on_flat_domain():
    s = scale_linear().domain((5, 5)).nice()
    assert s.domain() == [5, 5]
    assert not math.isnan(s(5))
