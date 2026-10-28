"""Coverage for Join.join()'s string shorthand (enter='shape_name') and
SceneAdapter.creator() -- the base/mock side of this only needs to
refuse clearly; the real implementation lives in LiveBlenderAdapter
(see tests/blender/test_join_creator.py)."""

import pytest

from d3blender import select
from d3blender.mock import new_scene


def test_creator_on_base_adapter_raises_clearly():
    adapter, chart = new_scene('Chart')
    with pytest.raises(NotImplementedError, match='LiveBlenderAdapter'):
        adapter.creator('uv_sphere', chart)


def test_join_string_shorthand_dispatches_through_creator():
    adapter, chart = new_scene('Chart')
    data = [{'label': 'a'}]
    with pytest.raises(NotImplementedError, match='LiveBlenderAdapter'):
        (select(adapter, '#Chart mesh')
            .data(data, key=lambda i, d: d['label'])
            .join('uv_sphere', collection=chart))


def test_join_creator_kwargs_with_a_callable_enter_is_a_hard_error():
    adapter, chart = new_scene('Chart')
    data = [{'label': 'a'}]

    def enter(d):
        raise AssertionError('should never be called -- the TypeError happens first')

    with pytest.raises(TypeError, match='creator kwargs'):
        (select(adapter, '#Chart mesh')
            .data(data, key=lambda i, d: d['label'])
            .join(enter, radius=2.0))
