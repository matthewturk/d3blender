"""Run this directory's real-bpy pytest suite inside the full Blender
*application*, not the PyPI `bpy` wheel -- the only way to check a
Blender version newer than the newest wheel (5.2.0 as of writing; this
project targets 5.3+). Not collected by pytest itself (no `test_`
prefix); run it through Blender:

    /path/to/blender --background --factory-startup \\
        --python tests/blender/run_in_blender_app.py [-- extra pytest args]

Exits with pytest's own exit code.

Two sys.path adjustments, both deliberate:

- This checkout's `src/` is *prepended*, so the d3blender under test is
  always this tree -- not whatever copy a Blender startup script or an
  editable install from another project's venv happens to put on the
  path first. The resolved `d3blender.__file__` is printed and checked
  so the log says exactly which copy ran.
- `.venv-blender`'s site-packages is *appended* (pytest, and
  beautifulsoup4/soupsieve if Blender's own Python lacks them). Both
  Pythons are 3.13. Appending, not prepending, means Blender's own
  modules always win; the PyPI `bpy` wheel sitting in that venv is never
  imported, because the application's built-in `bpy` is already in
  `sys.modules` before this script runs.
"""

import glob
import os
import sys

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, 'src')

sys.path.insert(0, SRC)
for site in glob.glob(os.path.join(REPO, '.venv-blender', 'lib', 'python3*', 'site-packages')):
    if site not in sys.path:
        sys.path.append(site)

# A copy imported by a startup script before this ran would win over the
# sys.path change above -- drop it so the import below resolves fresh.
for name in [m for m in sys.modules if m == 'd3blender' or m.startswith('d3blender.')]:
    del sys.modules[name]

import d3blender  # noqa: E402
import pytest  # noqa: E402

print(f'[run_in_blender_app] Blender {bpy.app.version_string}, Python {sys.version.split()[0]}')
print(f'[run_in_blender_app] d3blender imported from {d3blender.__file__}')
if os.path.realpath(os.path.dirname(d3blender.__file__)) != os.path.realpath(os.path.join(SRC, 'd3blender')):
    print('[run_in_blender_app] ERROR: that is not this checkout\'s src/d3blender')
    sys.exit(2)

extra = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
# -p no:cacheprovider: don't write .pytest_cache from inside Blender.
code = pytest.main([os.path.join(REPO, 'tests', 'blender'), '-p', 'no:cacheprovider', *extra])
sys.exit(int(code))
