"""
scale.py — d3's scaleLinear / scaleBand / scaleOrdinal / scaleTime /
scaleSequential, the thing that turns "data value" into "position/size/
color" everywhere else assumes exists. Deliberately tiny; this is the
whole reason d3 code reads as "describe the mapping, not the loop."

Every scale is a callable object that can be built two ways, and both
stay supported:

    height = scale_linear((0, 24), (0.2, 4.0))                        # original call form
    height = scale_linear().domain((0, 24)).range((0.2, 4.0)).nice()   # d3 chaining

Setters return the scale itself (so they chain); calling one with no
argument is a getter, same as d3. Continuous ranges can be numbers or
equal-length tuples (positions, RGBA colors), interpolated per component.
"""

import copy as _copy
import datetime as _datetime
import math as _math

_MISSING = object()


def _timestamp(value):
    """scale_time()'s date->number step. Accepts datetime.datetime,
    datetime.date, or an already-numeric value (so scale_time also just
    works against a domain you've already converted yourself). Naive
    datetimes are treated as local time, same as Python's own
    datetime.timestamp() -- fine for "which day is this" charting, not
    guaranteed correct across mixed timezones, same class of simplification
    as array.bin()'s fixed-width bins."""
    if isinstance(value, _datetime.datetime):
        return value.timestamp()
    if isinstance(value, _datetime.date):
        return _datetime.datetime.combine(value, _datetime.time.min).timestamp()
    return value


def _lerp(a, b, t):
    """Interpolate numbers, or tuples/lists component-wise (vectors,
    RGBA colors) -- d3 interpolates arrays the same way."""
    if isinstance(a, (tuple, list)):
        return tuple(_lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t


# -- d3-array's tick math ("nice" round steps: 1, 2 or 5 x 10^k) -------------

_E10, _E5, _E2 = _math.sqrt(50), _math.sqrt(10), _math.sqrt(2)


def _tick_increment(start, stop, count):
    """d3.tickIncrement: a positive step for steps >= 1, or the negative
    *inverse* of the step for steps < 1 (keeps 0.1-style steps exact)."""
    step = (stop - start) / max(1, count)
    power = _math.floor(_math.log10(step))
    error = step / 10 ** power
    factor = 10 if error >= _E10 else 5 if error >= _E5 else 2 if error >= _E2 else 1
    if power >= 0:
        return factor * 10 ** power
    return -(10 ** -power) / factor


def ticks(start, stop, count=10):
    """d3.ticks: about `count` round values covering [start, stop], with
    a step of 1, 2 or 5 times a power of ten. Values are computed as
    integers divided by an exact factor so they print cleanly (0.3, not
    0.30000000000000004)."""
    if start == stop:
        return [start]
    reverse = stop < start
    if reverse:
        start, stop = stop, start
    inc = _tick_increment(start, stop, count)
    if inc < 0:
        inv = -inc
        i1, i2 = _math.ceil(start * inv - 1e-9), _math.floor(stop * inv + 1e-9)
        values = [i / inv for i in range(i1, i2 + 1)]
    else:
        i1, i2 = _math.ceil(start / inc - 1e-9), _math.floor(stop / inc + 1e-9)
        values = [i * inc for i in range(i1, i2 + 1)]
    return values[::-1] if reverse else values


def _nice(d0, d1, count=10):
    """Extend [d0, d1] outward to round values -- d3's linearish nice()."""
    if d0 == d1:
        return d0, d1
    reverse = d1 < d0
    lo, hi = (d1, d0) if reverse else (d0, d1)
    prestep = None
    for _ in range(10):
        step = _tick_increment(lo, hi, count)
        if step == prestep:
            break
        if step > 0:
            lo, hi = _math.floor(lo / step) * step, _math.ceil(hi / step) * step
        else:
            lo, hi = _math.ceil(lo * step) / step, _math.floor(hi * step) / step
        prestep = step
    return (hi, lo) if reverse else (lo, hi)


class _Scale:
    """Shared plumbing for every scale: copy()."""

    def copy(self):
        return _copy.copy(self)


class _ContinuousScale(_Scale):
    """Two-point domain -> two-point range, linear in between. Subclasses
    only change how a domain value becomes a number (_to_num) and back
    (_from_num), which is all scale_time needs."""

    def __init__(self, domain=(0, 1), range_=(0, 1)):
        self._domain = tuple(domain)
        self._range = tuple(range_)
        self._clamp = False

    def _to_num(self, x):
        return x

    def _from_num(self, x):
        return x

    def __call__(self, x):
        d0, d1 = (self._to_num(v) for v in self._domain)
        span = d1 - d0
        t = (self._to_num(x) - d0) / span if span else 0
        if self._clamp:
            t = max(0.0, min(1.0, t))
        return _lerp(self._range[0], self._range[1], t)

    def invert(self, y):
        """Range value -> domain value. Numeric ranges only."""
        d0, d1 = (self._to_num(v) for v in self._domain)
        r0, r1 = self._range
        t = (y - r0) / (r1 - r0) if r1 != r0 else 0
        if self._clamp:
            t = max(0.0, min(1.0, t))
        return self._from_num(d0 + t * (d1 - d0))

    def domain(self, *values):
        """Getter with no argument; setter with one iterable (`.domain((0, 10))`)."""
        if not values:
            return list(self._domain)
        self._domain = tuple(values[0])
        return self

    def range(self, *values):
        if not values:
            return list(self._range)
        self._range = tuple(values[0])
        return self

    def clamp(self, *value):
        """`.clamp()` / `.clamp(True)` turns clamping on, `.clamp(False)`
        off. Off by default, like d3 (scale_sequential is the exception)."""
        self._clamp = bool(value[0]) if value else True
        return self


class LinearScale(_ContinuousScale):
    def ticks(self, count=10):
        """About `count` round values across the domain (d3's scale.ticks)."""
        return ticks(self._domain[0], self._domain[1], count)

    def nice(self, count=10):
        """Extend the domain to round values, e.g. (0.2, 97) -> (0, 100)."""
        self._domain = _nice(self._domain[0], self._domain[1], count)
        return self


class TimeScale(_ContinuousScale):
    """d3.scaleTime -- a linear scale over a date/datetime domain (see
    _timestamp() for the conversion and its documented limits).
    `.invert(y)` returns a datetime, so it's a real inverse of what the
    scale accepts. No `.ticks()`/`.nice()`: d3's calendar-aware time
    ticks (days, months, ...) are a different algorithm from numeric
    ticks, and numeric ticks on timestamps would land on odd seconds."""

    def _to_num(self, x):
        return _timestamp(x)

    def _from_num(self, x):
        return _datetime.datetime.fromtimestamp(x)


def scale_linear(domain=(0, 1), range_=(0, 1)):
    """d3.scaleLinear. `scale_linear(domain, range_)`, or build it up with
    `.domain()`, `.range()`, `.nice()`, `.clamp()`; `.ticks(n)` and
    `.invert(y)` work on either form."""
    return LinearScale(domain, range_)


def scale_time(domain=(0, 1), range_=(0, 1)):
    """d3.scaleTime -- see TimeScale."""
    return TimeScale(domain, range_)


class SequentialScale(_Scale):
    """d3.scaleSequential -- maps a continuous domain through
    `interpolator(t)` for `t` in `[0, 1]`, instead of onto a fixed
    numeric range. **Clamps by default** -- unlike real d3, which only
    clamps if you opt in with `.clamp(true)` -- since an interpolator
    built for exactly `[0, 1]` (like `interpolate_rgb`) will typically
    produce nonsense (channel values outside 0-1) for out-of-domain input
    otherwise. `.clamp(False)` opts out."""

    def __init__(self, domain=(0, 1), interpolator=None):
        self._domain = tuple(domain)
        self._interpolator = interpolator or (lambda t: t)
        self._clamp = True

    def __call__(self, x):
        d0, d1 = self._domain
        span = d1 - d0
        t = (x - d0) / span if span else 0
        if self._clamp:
            t = max(0.0, min(1.0, t))
        return self._interpolator(t)

    def domain(self, *values):
        if not values:
            return list(self._domain)
        self._domain = tuple(values[0])
        return self

    def interpolator(self, *fn):
        if not fn:
            return self._interpolator
        self._interpolator = fn[0]
        return self

    def clamp(self, *value):
        self._clamp = bool(value[0]) if value else True
        return self

    def nice(self, count=10):
        self._domain = _nice(self._domain[0], self._domain[1], count)
        return self

    def ticks(self, count=10):
        return ticks(self._domain[0], self._domain[1], count)


def scale_sequential(domain=(0, 1), interpolator=None):
    """d3.scaleSequential. `scale_sequential(domain, interpolator)`, or
    `scale_sequential(interpolator)` (d3's one-argument form, domain
    [0, 1]), or chained: `scale_sequential().domain(...).interpolator(...)`."""
    if callable(domain) and interpolator is None:
        domain, interpolator = (0, 1), domain
    return SequentialScale(domain, interpolator)


class BandScale(_Scale):
    """d3.scaleBand: one equal band per domain item across the range.
    `padding` is the fraction of each step left empty, split evenly on
    both sides of the band (simpler than d3's separate inner/outer
    padding and align). `step` is a plain number attribute (not d3's
    `step()` method), kept that way because existing code reads it as
    `x.step`; `bandwidth()` is a method, as in d3. An item not in the
    domain raises KeyError (unchanged from before)."""

    def __init__(self, domain=(), range_=(0, 1), padding=0.1):
        self._domain = list(domain)
        self._range = tuple(range_)
        self._padding = padding

    @property
    def step(self):
        n = len(self._domain)
        r0, r1 = self._range
        return (r1 - r0) / n if n else 0

    def bandwidth(self):
        return self.step * (1 - self._padding)

    def __call__(self, item):
        if item not in self._domain:
            raise KeyError(item)
        step = self.step
        return self._range[0] + step * self._domain.index(item) + (step - self.bandwidth()) / 2

    def domain(self, *values):
        if not values:
            return list(self._domain)
        self._domain = list(values[0])
        return self

    def range(self, *values):
        if not values:
            return list(self._range)
        self._range = tuple(values[0])
        return self

    def padding(self, *value):
        if not value:
            return self._padding
        self._padding = value[0]
        return self


def scale_band(domain_items=(), range_=(0, 1), padding=0.1):
    """d3.scaleBand -- see BandScale."""
    return BandScale(domain_items, range_, padding)


class OrdinalScale(_Scale):
    """d3.scaleOrdinal: domain item i -> range[i % len(range)].

    Unknown items: if the scale was given an explicit domain, they map to
    `range[0]` (this library's original behaviour, kept), or to whatever
    `.unknown(value)` set. If no domain was ever given, the domain is
    *implicit*, like d3's: each new item is appended on first use, so
    `scale_ordinal(range_=palette)` hands out colors in order of
    appearance."""

    def __init__(self, domain=None, range_=()):
        self._implicit = domain is None
        self._domain = list(domain) if domain is not None else []
        self._range = list(range_)
        self._unknown = _MISSING

    def __call__(self, item):
        if item in self._domain:
            return self._range[self._domain.index(item) % len(self._range)]
        if self._implicit:
            self._domain.append(item)
            return self._range[(len(self._domain) - 1) % len(self._range)]
        if self._unknown is not _MISSING:
            return self._unknown
        return self._range[0]

    def domain(self, *values):
        if not values:
            return list(self._domain)
        self._domain = list(values[0])
        self._implicit = False
        return self

    def range(self, *values):
        if not values:
            return list(self._range)
        self._range = list(values[0])
        return self

    def unknown(self, *value):
        if not value:
            return None if self._unknown is _MISSING else self._unknown
        self._unknown = value[0]
        return self


def scale_ordinal(domain_items=None, range_=()):
    """d3.scaleOrdinal -- see OrdinalScale."""
    return OrdinalScale(domain_items, range_)


def interpolate_rgb(start, end):
    """d3.interpolateRgb -- linear interpolation between two color
    tuples (3-channel RGB or 4-channel RGBA, as long as `start`/`end`
    match), for use as `scale_sequential()`'s interpolator. Not a full
    d3-interpolate port (no color-space-aware interpolation, no other
    value types) -- the one common case, kept alongside scale_sequential
    since that's its only real use here rather than a whole separate
    module for one function."""
    def interpolator(t):
        return tuple(a + (b - a) * t for a, b in zip(start, end))
    return interpolator
