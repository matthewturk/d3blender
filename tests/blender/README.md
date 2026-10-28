# Real-`bpy` tests

Everything under `tests/` at the top level runs against `d3blender.mock`
-- no Blender required, and that's still the primary, fast (~160 tests
in well under a second) suite you get from a plain `pytest` at the repo
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

A whole-repo `.venv-blender/bin/pytest` (no path) runs both suites in
one go. That works because `pyproject.toml` sets
`--import-mode=importlib`: `tests/` and `tests/blender/` intentionally
share some test-file basenames (`test_points.py`, `test_point_attrs.py`,
`test_join_creator.py`), and pytest's default import mode refuses that
with "import file mismatch".

## Running against the full Blender application (newer than the wheel)

The PyPI wheel lags real releases, so this same suite can also run
inside an installed Blender binary, which is how anything past 5.2 gets
checked:

```bash
/path/to/blender --background --factory-startup \
    --python tests/blender/run_in_blender_app.py -- -q
```

`run_in_blender_app.py` prepends this checkout's `src/` (and drops any
d3blender a startup script already imported), appends `.venv-blender`'s
site-packages for pytest/bs4 (both are Python 3.13; the app's own
built-in `bpy` always wins over the wheel), prints which `d3blender`
file it imported, refuses to run if that isn't this checkout, and exits
with pytest's exit code. `.venv-blender` must exist (see Setup).

Two things worth knowing:

- **`--factory-startup` does not stop user startup scripts from
  running.** A user config's startup scripts (here: an extension sync
  and several `load_post` handlers) still run at launch and on every
  file load.
- **Expect ~30 s in the app vs. ~2 s on the wheel.** It used to be ~5
  minutes: the `clean_scene` fixture called
  `read_factory_settings(use_empty=True)`, which also resets
  *preferences* and so re-registers every enabled add-on/extension
  (~3.2 s per call in Blender 5.4, twice per test). It now uses
  `read_homefile(use_empty=True, use_factory_startup=True)` (~0.28 s
  in-app, ~0.01 s on the wheel). Checked: the resulting `bpy.data`
  state is identical on both 5.2 and 5.4. What's left of the gap is
  mostly the user's `load_post` handlers, which run on every reset.
  Preferences are no longer reset between tests, so keep
  `--factory-startup` on the command line.
- If one of those startup scripts puts a *different* d3blender on
  `sys.path` (an editable install from another project's venv), the
  runner's own `sys.path`/`sys.modules` handling still makes this
  checkout's copy the one under test; check the printed path.

## Why this is a separate suite, not folded into the main one

- **Heavyweight, real dependency.** `bpy` is a ~380MB download and only
  targets one Python version -- not something the fast mock-backed suite
  should ever require.
- **Process-global, mutable state.** Real `bpy.data` is a singleton --
  tests here reset it (`bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)`)
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

**Last full in-app run:** Blender 5.4.0 Alpha (Python 3.13.13), 57 of 57
passed in ~35 s with no warnings, `d3blender` imported from this
checkout's `src/`. On the 5.2 wheel the same suite is 56 passed, 1
skipped (the `compositor_effects`-only test). The compositor tests take
the `scene.compositor_effects` path where it exists and the deprecated
`compositing_node_group`/`use_nodes` path otherwise (see the README's
"Compositor nodes" section). That
includes the Geometry Nodes tests below for float, int, bool, vector,
object and material sockets -- i.e. `modifier.properties.inputs[identifier]`
is still an `IDPropertyGroup` read/written via `["value"]` on 5.4, and
`modifier[identifier] = v` still raises there.

`test_ergonomics.py` covers the adapter-less `select()`, `select_all()` +
`join('cube')` reruns, parent-linking and `transition()` keyframes;
`test_script_runner_examples.py` runs `examples/script_runner/*.py`
through `execute(context, params)` the way Script Runner does, with
reruns and setting changes.

Covered: the `LiveBlenderAdapter`-specific overrides (`remove()`,
`get_or_create_collection()`, `create_line_mesh()`), plus `get_attr`/
`set_attr` against real modifiers -- both a plain (non-GN) property and
a real Geometry Nodes input, the exact path that broke against real 5.2+
Blender (see the fix commit this directory was added alongside).

Not covered, still open per CLAUDE.md: `examples/geometry_nodes_countries.py`
and `examples/scatter_plot_3d_blender.py`, since those additionally need
`databpy`/`nodebpy` installed -- a real Blender application, not just
the headless `bpy` module those examples don't strictly require either.
