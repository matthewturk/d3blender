from d3blender.shape import line
from d3blender.mock import new_scene


def test_line_empty_and_single_point_have_no_segments():
    assert line([]) == []
    assert line([(0, 0, 0)]) == []


def test_line_connects_consecutive_points():
    points = [(0, 0, 0), (1, 0, 0), (1, 1, 0)]
    assert line(points) == [
        ((0, 0, 0), (1, 0, 0)),
        ((1, 0, 0), (1, 1, 0)),
    ]


def test_line_closed_also_connects_last_point_back_to_first():
    points = [(0, 0, 0), (1, 0, 0), (1, 1, 0)]
    assert line(points, closed=True) == [
        ((0, 0, 0), (1, 0, 0)),
        ((1, 0, 0), (1, 1, 0)),
        ((1, 1, 0), (0, 0, 0)),
    ]


def test_line_two_points_is_a_single_segment():
    assert line([(0, 0, 0), (5, 0, 0)]) == [((0, 0, 0), (5, 0, 0))]


def test_line_feeds_create_line_mesh_directly():
    adapter, chart = new_scene('Chart')
    points = [(0, 0, 0), (1, 1, 0), (2, 0, 0), (3, 1, 0)]

    obj = adapter.create_line_mesh(chart, 'Path', line(points))

    vertices, edges = obj.mesh_data
    assert len(vertices) == 2 * 3  # one vertex pair per segment
    assert len(edges) == 3
