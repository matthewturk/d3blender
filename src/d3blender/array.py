"""
array.py — small numeric helpers mirroring pieces of d3-array: bin(),
extent(), max(), min(). Deliberately tiny, same spirit as scale.py.

Not flattened into the top-level `d3blender` package the way scale.py's
functions are: `max`/`min`/`bin` collide with Python builtins, so import
this module explicitly -- `from d3blender import array` -- and call
`array.max(...)` / `array.bin(...)`, mirroring d3's own `d3.max(...)`
namespacing.
"""

import builtins


def extent(items, value=None):
    """(min, max) of `value(d)` over `items`, skipping None values.
    (None, None) if `items` is empty or every value is None."""
    accessor = value or (lambda d: d)
    vals = [v for v in (accessor(d) for d in items) if v is not None]
    if not vals:
        return (None, None)
    return (builtins.min(vals), builtins.max(vals))


def max(items, value=None):
    return extent(items, value)[1]


def min(items, value=None):
    return extent(items, value)[0]


class Bin(list):
    """The items that fell in [x0, x1) (the last bin is right-inclusive),
    with the bin edges attached as attributes -- close enough to a
    d3.bin() result that `len(some_bin)` (the frequency) and
    `some_bin.x0`/`.x1` read the same as the JS version."""

    def __init__(self, x0, x1, items=()):
        super().__init__(items)
        self.x0 = x0
        self.x1 = x1

    def __repr__(self):
        return f'Bin(x0={self.x0!r}, x1={self.x1!r}, n={len(self)})'


def bin(items, value=None, thresholds=10):
    """Bucket `items` into `thresholds` equal-width bins spanning the
    extent of `value(d)` (or `d` itself) -- mirrors
    `d3.bin().thresholds(n).value(fn)(items)`, simplified to fixed-width
    bins rather than d3's "nice" auto-rounded edges (a stated limitation,
    not an oversight -- add real "nice" rounding if you need axis ticks
    to land on round numbers).

    `array.max(bins, value=len)` gives the tallest bin, same idiom as
    d3's `d3.max(bins, d => d.length)`.
    """
    accessor = value or (lambda d: d)
    lo, hi = extent(items, accessor)
    if lo is None:
        return []
    span = hi - lo
    width = span / thresholds if span else 1
    bins = [Bin(lo + i * width, lo + (i + 1) * width) for i in range(thresholds)]
    for d in items:
        v = accessor(d)
        if v is None:
            continue
        idx = int((v - lo) / width) if span else 0
        bins[builtins.min(idx, thresholds - 1)].append(d)
    return bins
