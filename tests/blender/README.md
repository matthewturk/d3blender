# Real-`bpy` tests

Everything under `tests/` at the top level runs against `d3blender.mock`
-- no Blender required, and that's still the primary, fast (~53 tests in
well under a second) suite you get from a plain `pytest` at the repo
root. This directory is different: it imports the real `bpy` module and
exercises `blender_adapter.py`'s `LiveBlenderAdapter`, the one file in
this package that has historically gone unverified against a live
Blender install (see CLAUDE.md's "Testing status").

## Setup (one-time)

PyPI publishes a headless `bpy` module -- real Blender, importable
directly, no application download or `--background --python` subprocess
dance needed. It only ships `cp313` wheels, though, so it needs its own
venv independent of whatever Python the rest of this project's dev venv
uses:

```bash
uv venv --python 3.13 .venv-blender
uv pip install --python .venv-blender/bin/python -e ".[dev,blender-test]"
```

## Running

```bash
.venv-blender/bin/pytest tests/blender
```

A plain `pytest` (or `pytest tests/`) from the main dev venv **skips**
this directory instead of failing -- `tests/blender/conftest.py` calls
`pytest.importorskip("bpy")`, so importing `bpy` from a venv that
doesn't have it reports as one skip, not a collection error. You'll only
see these tests actually run from `.venv-blender`.

## Why this is a separate suite, not folded into the main one

- **Heavyweight, real dependency.** `bpy` is a ~380MB download and only
  targets one Python version -- not something the fast mock-backed suite
  should ever require.
- **Process-global, mutable state.** Real `bpy.data` is a singleton --
  tests here reset it (`bpy.ops.wm.read_factory_settings(use_empty=True)`)
  between cases via the `clean_scene` autouse fixture in `conftest.py`,
  which is a different isolation model than the mock's fresh-object-per-test
  approach.
- **Version drift is real and expected.** PyPI's `bpy` wheel lags actual
  Blender releases (pinned to `5.2.0` in `pyproject.toml`'s
  `blender-test` extra as of writing; this project targets 5.3+ -- same
  gap noted for `nodebpy` in CLAUDE.md). If a test here fails after a
  Blender/`bpy` version bump, that's a real compatibility break to
  investigate, not a flaky test -- see the Geometry Nodes input tests
  in particular, which pin down an exact storage-shape assumption
  (`modifier.properties.inputs[identifier]`, an `IDPropertyGroup`
  accessed via `["value"]`) that already changed once, in 5.2 (see
  CLAUDE.md's Geometry Nodes section).

## What's covered here vs. what isn't

Covered: the `LiveBlenderAdapter`-specific overrides (`remove()`,
`get_or_create_collection()`, `create_line_mesh()`), plus `get_attr`/
`set_attr` against real modifiers -- both a plain (non-GN) property and
a real Geometry Nodes input, the exact path that broke against real 5.2+
Blender (see the fix commit this directory was added alongside).

Not covered, still open per CLAUDE.md: `examples/geometry_nodes_countries.py`
and `examples/scatter_plot_3d_blender.py`, since those additionally need
`databpy`/`nodebpy` installed -- a real Blender application, not just
the headless `bpy` module those examples don't strictly require either.
