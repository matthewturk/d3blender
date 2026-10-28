"""
d3blender -- a d3.js-flavored, adapter-agnostic query/selection/animation
layer over Blender's scene graph.

    import d3blender as d3

    rows = d3.csv('sales.csv')
    chart = d3.collection('Chart')
    y = d3.scale_linear().domain((0, d3.array.max(rows, lambda d: d['revenue']))).nice().range((0, 4))
    bars = (d3.select_all(chart)
              .data(rows, key='month')
              .join('cube')
              .attr('location', lambda el, d, i: (i * 1.5, 0, y(d['revenue']) / 2)))

Everything here is pure Python and testable without Blender installed
(see d3blender.mock for a fake scene). To use it inside Blender itself,
see d3blender.blender_adapter.get_adapter().
"""

from .adapter import SceneAdapter
from .query import (
    select,
    select_all,
    collection,
    compile_query,
    set_default_adapter,
    default_adapter,
)
from .selection import Selection, Join, Transition
from .fetch import csv, tsv, dsv, json, auto_type, auto_type_value
from . import array
from .scale import (
    scale_linear,
    scale_band,
    scale_ordinal,
    scale_time,
    scale_sequential,
    interpolate_rgb,
    ticks,
)

__all__ = [
    "SceneAdapter",
    "select",
    "select_all",
    "collection",
    "compile_query",
    "set_default_adapter",
    "default_adapter",
    "Selection",
    "Join",
    "Transition",
    "auto_type",
    "auto_type_value",
    "ticks",
    "scale_linear",
    "scale_band",
    "scale_ordinal",
    "scale_time",
    "scale_sequential",
    "interpolate_rgb",
]

# csv/tsv/dsv/json are deliberately left out of __all__: a star-import
# would shadow the stdlib csv/json modules. Use them as d3blender.csv(...)
# (e.g. `import d3blender as d3; d3.csv(path)`).

__version__ = "0.1.0"
