from d3blender import scale_linear
from d3blender.axis import ticks, tick_lines


def test_ticks_evenly_spaced():
    assert ticks((0, 20), count=5) == [0, 5, 10, 15, 20]


def test_ticks_single_count_returns_domain_start():
    assert ticks((3, 7), count=1) == [3]


def test_tick_lines_computes_segments_along_caller_chosen_plane():
    scale = scale_linear(domain=(0, 10), range_=(0, 100))
    segments = tick_lines(
        scale, [0, 5, 10],
        place=lambda p: (p, 0, 0),
        tick_vector=(0, -1, 0),
    )
    assert segments == [
        ((0, 0, 0), (0, -1, 0)),
        ((50, 0, 0), (50, -1, 0)),
        ((100, 0, 0), (100, -1, 0)),
    ]


def test_tick_lines_empty_values():
    scale = scale_linear(domain=(0, 10), range_=(0, 100))
    assert tick_lines(scale, [], place=lambda p: (p, 0, 0), tick_vector=(0, -1, 0)) == []
