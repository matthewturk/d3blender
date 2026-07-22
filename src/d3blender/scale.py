"""
scale.py — d3's scaleLinear / scaleBand / scaleOrdinal, the thing that
turns "data value" into "position/size/color" everywhere else assumes
exists. Deliberately tiny; this is the whole reason d3 code reads as
"describe the mapping, not the loop."
"""


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
