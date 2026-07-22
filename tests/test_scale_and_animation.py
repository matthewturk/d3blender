from d3blender import select, scale_linear, scale_band, scale_ordinal
from d3blender.mock import MockObject


def test_scale_linear():
    height = scale_linear(domain=(0, 24), range_=(0.2, 4.0))
    assert height(0) == 0.2
    assert height(24) == 4.0
    assert round(height(12), 4) == round((0.2 + 4.0) / 2, 4)


def test_scale_band_spacing_and_bandwidth():
    x = scale_band(['Jan', 'Feb', 'Mar', 'Apr'], range_=(0, 8), padding=0.2)
    assert x('Jan') < x('Feb') < x('Mar') < x('Apr')
    assert 0 < x.bandwidth() < x.step


def test_scale_ordinal_cycles():
    color = scale_ordinal(['a', 'b'], range_=['red', 'blue'])
    assert color('a') == 'red'
    assert color('b') == 'blue'


def test_keyframe_records_value_and_frame(scene):
    props = next(c for c in scene.collections if c.name == 'Props')
    box = MockObject('Box', 'MESH')
    props.objects.append(box)
    box.users_collection = (props,)
    scene.objects.append(box)

    sel = select(scene, '#Box')
    sel.keyframe(1, location=(0, 0, 0))
    sel.keyframe(25, location=(4, 0, 0))

    assert box._keyframes == [
        (1, 'location', (0, 0, 0)),
        (25, 'location', (4, 0, 0)),
    ]
