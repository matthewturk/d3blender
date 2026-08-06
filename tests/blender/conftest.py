"""`pytest.importorskip` here -- not a plain `import bpy` -- is what lets
a bare `pytest` from the main dev venv (no `bpy` installed) skip this
whole directory instead of erroring out collection. See README.md in
this directory for how to actually run these tests."""

import pytest

bpy = pytest.importorskip("bpy")

pytestmark = pytest.mark.blender


@pytest.fixture(autouse=True)
def clean_scene():
    """Real `bpy.data` is process-global, unlike the mock's fresh objects
    per test -- reset to Blender's empty factory state before *and* after
    each test so state never leaks between cases (before: in case a
    previous test crashed mid-test and skipped its own cleanup; after:
    so the next test, or a REPL poking at the same process, starts
    clean)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    yield
    bpy.ops.wm.read_factory_settings(use_empty=True)


@pytest.fixture
def spawn():
    """Real-bpy equivalent of d3blender.mock's MockObject + linking dance
    -- create a mesh object, link it into a collection, and stamp custom
    properties. Test scaffolding only, mirroring mock.spawn()'s role for
    the mock suite (see CLAUDE.md). A fixture (returning a factory
    function), not a plain module function, so test files can grab it
    without relying on `tests/blender/` being an importable package."""

    def _spawn(name, collection, **props):
        obj = bpy.data.objects.new(name, bpy.data.meshes.new(f'{name}Mesh'))
        collection.objects.link(obj)
        for key, value in props.items():
            obj[key] = value
        return obj

    return _spawn
