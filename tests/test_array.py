from d3blender import array


def test_extent_basic():
    assert array.extent([3, 1, 4, 1, 5]) == (1, 5)


def test_extent_with_accessor_skips_none():
    items = [{'v': 3}, {'v': None}, {'v': 7}]
    assert array.extent(items, value=lambda d: d['v']) == (3, 7)


def test_extent_empty_is_none_none():
    assert array.extent([]) == (None, None)


def test_max_and_min():
    items = [{'v': 3}, {'v': 7}, {'v': -2}]
    assert array.max(items, value=lambda d: d['v']) == 7
    assert array.min(items, value=lambda d: d['v']) == -2


def test_bin_covers_every_item_across_the_extent():
    data = [{'rate': r} for r in [0, 1.2, 2.5, 3.9, 5.0, 4.9, 0.1]]
    bins = array.bin(data, value=lambda d: d['rate'], thresholds=5)
    assert len(bins) == 5
    assert bins[0].x0 == 0
    assert bins[-1].x1 == 5.0
    assert sum(len(b) for b in bins) == len(data)


def test_bin_max_value_is_the_boundary_and_lands_in_last_bin():
    data = [{'rate': 0}, {'rate': 10}]
    bins = array.bin(data, value=lambda d: d['rate'], thresholds=2)
    assert [len(b) for b in bins] == [1, 1]


def test_bin_all_identical_values_go_in_first_bin():
    data = [{'rate': 5}] * 4
    bins = array.bin(data, value=lambda d: d['rate'], thresholds=4)
    assert [len(b) for b in bins] == [4, 0, 0, 0]


def test_bin_empty_input():
    assert array.bin([], value=lambda d: d['rate'], thresholds=10) == []


def test_max_of_bins_by_length_mirrors_d3_max_bins_length():
    data = [{'rate': r} for r in [1, 1, 1, 2, 3]]
    bins = array.bin(data, value=lambda d: d['rate'], thresholds=3)
    assert array.max(bins, value=len) == 3
