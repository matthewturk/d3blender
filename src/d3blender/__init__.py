"""
d3blender -- a d3.js-flavored, adapter-agnostic query/selection/animation
layer over Blender's scene graph.

    from d3blender import select, scale_linear

Everything here is pure Python and testable without Blender installed
(see d3blender.mock for a fake scene). To use it inside Blender itself,
see d3blender.blender_adapter.get_adapter().
"""

from .adapter import SceneAdapter
from .query import select, compile_query
from .selection import Selection, Join
from .scale import (
    scale_linear,
    scale_band,
    scale_ordinal,
    scale_time,
    scale_sequential,
    interpolate_rgb,
)

__all__ = [
    "SceneAdapter",
    "select",
    "compile_query",
    "Selection",
    "Join",
    "scale_linear",
    "scale_band",
    "scale_ordinal",
    "scale_time",
    "scale_sequential",
    "interpolate_rgb",
]

__version__ = "0.1.0"
