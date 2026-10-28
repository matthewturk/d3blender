"""
scale.py — d3's scaleLinear / scaleBand / scaleOrdinal / scaleTime /
scaleSequential, the thing that turns "data value" into "position/size/
color" everywhere else assumes exists. Deliberately tiny; this is the
whole reason d3 code reads as "describe the mapping, not the loop."
"""

import datetime as _datetime


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


def scale_linear(domain, range_):
    d0, d1 = domain
    r0, r1 = range_
    span = d1 - d0

    def scale(x):
        t = (x - d0) / span if span else 0
        return r0 + t * (r1 - r0)

    scale.invert = lambda y: d0 + ((y - r0) / (r1 - r0)) * span
    return scale


def scale_band(domain_items, range_, padding=0.1):
    domain_items = list(domain_items)
    n = len(domain_items)
    r0, r1 = range_
    step = (r1 - r0) / n if n else 0
    bandwidth = step * (1 - padding)
    offset = (step - bandwidth) / 2
    positions = {item: r0 + step * i + offset for i, item in enumerate(domain_items)}

    def scale(item):
        return positions[item]

    scale.bandwidth = lambda: bandwidth
    scale.step = step
    return scale


def scale_ordinal(domain_items, range_):
    domain_items = list(domain_items)
    mapping = {item: range_[i % len(range_)] for i, item in enumerate(domain_items)}

    def scale(item):
        return mapping.get(item, range_[0])

    return scale


def scale_time(domain, range_):
    """d3.scaleTime -- scale_linear with a date/datetime domain instead
    of a plain numeric one (see _timestamp() above for the conversion
    and its documented limits). `.invert(y)` returns a datetime, not a
    raw number, so it's a real inverse of what `scale()` accepts."""
    d0, d1 = _timestamp(domain[0]), _timestamp(domain[1])
    r0, r1 = range_
    span = d1 - d0

    def scale(x):
        t = (_timestamp(x) - d0) / span if span else 0
        return r0 + t * (r1 - r0)

    scale.invert = lambda y: _datetime.datetime.fromtimestamp(
        d0 + ((y - r0) / (r1 - r0)) * span)
    return scale


def scale_sequential(domain, interpolator):
    """d3.scaleSequential -- maps a continuous domain through
    `interpolator(t)` for `t` in `[0, 1]`, instead of onto a fixed
    numeric range. `interpolator` is any `t -> value` callable --
    `interpolate_rgb()` below for the common color case, or your own for
    anything else (a shape parameter, an opacity curve, ...). Clamps `t`
    to `[0, 1]` before calling `interpolator` -- unlike real d3, which
    only clamps if you opt in with `.clamp(true)` -- since an
    interpolator built for exactly `[0, 1]` (like `interpolate_rgb`)
    will typically produce nonsense (channel values outside 0-1) for
    out-of-domain input otherwise; deliberately safer by default here."""
    d0, d1 = domain
    span = d1 - d0

    def scale(x):
        t = (x - d0) / span if span else 0
        t = max(0.0, min(1.0, t))
        return interpolator(t)

    return scale


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
