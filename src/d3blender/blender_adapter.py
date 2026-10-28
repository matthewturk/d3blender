"""
blender_adapter.py -- the only file in this package that imports bpy.
Everything else is bpy-agnostic and testable without Blender installed
(see d3blender.mock for the fake scene used by the test suite).

    import bpy
    from d3blender.blender_adapter import get_adapter
    from d3blender import select

    adapter = get_adapter()
    select(adapter, 'mesh:selected').attr('hp', 100)

Call get_adapter() fresh whenever the scene may have changed (new objects,
new collections) rather than holding onto one instance for a whole
session -- it's a cheap call, and this avoids stale-index bugs. See the
README section "Live vs. cached" for why this is a deliberate trade-off.

NOTE: this file is written against the documented, stable parts of
bpy's API (bpy.data.objects/collections, obj.type/.parent/.users_collection,
Collection.objects/.children, ID.keys()/.get()/[]), but has not yet been
exercised against a live Blender install by the maintainers -- if
something in here doesn't match your Blender version, please open an
issue with the version number and the mismatch.
"""

from .adapter import (
    SceneAdapter,
    _segments_to_vertices_edges,
    _check_point_count,
    _infer_point_attr_type,
    _POINT_ATTR_SHAPE,
)
from .points import point_data

# Join.join()'s string-shorthand registry (see Join.join()'s docstring
# and LiveBlenderAdapter.creator() below) -- name -> (bpy.ops.mesh
# function name, default creation kwargs). Deliberately just the
# standard mesh primitives Blender itself ships as one-call operators;
# this is a dispatch table to real bpy.ops, not a hand-rolled geometry
# generator (see CLAUDE.md's "no primitive-mesh functions" discussion --
# adding entries here should mean "another bpy.ops.mesh.primitive_*_add
# exists," never "and here's our own vertex math for it").
_PRIMITIVE_OPS = {
    'uv_sphere': ('primitive_uv_sphere_add', {'radius': 1.0, 'segments': 32, 'ring_count': 16}),
    'ico_sphere': ('primitive_ico_sphere_add', {'radius': 1.0, 'subdivisions': 2}),
    'cube': ('primitive_cube_add', {'size': 2.0}),
    'cylinder': ('primitive_cylinder_add', {'radius': 1.0, 'depth': 2.0, 'vertices': 32}),
    'cone': ('primitive_cone_add', {'radius1': 1.0, 'depth': 2.0, 'vertices': 32}),
    'plane': ('primitive_plane_add', {'size': 2.0}),
    'torus': ('primitive_torus_add', {}),
    'circle': ('primitive_circle_add', {'radius': 1.0, 'vertices': 32}),
}


class LiveBlenderAdapter(SceneAdapter):
    """Same as SceneAdapter, except remove() calls the real bpy.data
    removal APIs (which already handle unlinking) instead of the mock's
    manual list surgery, get_or_create_collection() creates a real bpy
    collection and links it into the scene, create_line_mesh() builds a
    real bpy mesh, and point_attr()/set_point_attr() use bulk foreach_get/
    foreach_set instead of SceneAdapter's per-vertex Python loop -- a real
    performance difference, not a behavior one (see below)."""

    def remove(self, el):
        import bpy

        if hasattr(el, 'objects') and hasattr(el, 'children'):
            bpy.data.collections.remove(el)
        else:
            bpy.data.objects.remove(el, do_unlink=True)

    def current_frame(self):
        import bpy

        return bpy.context.scene.frame_current

    def link(self, el, collection):
        """Real-bpy version of SceneAdapter.link()."""
        collection.objects.link(el)
        if not any(o == el for o in self.objects):
            self.objects.append(el)

    def get_or_create_collection(self, name, parent=None):
        """Same contract as SceneAdapter.get_or_create_collection(),
        except a real bpy.data.collections.new() result also needs
        linking into the scene (or a parent collection) to actually show
        up -- an unlinked collection is an orphan datablock, invisible in
        the outliner/viewport.

        With `parent` given, the lookup is scoped to `parent.children`
        (see the base docstring). Collection names are global in real
        Blender, so a new child whose name is already taken elsewhere
        comes back auto-suffixed ("Halos.001") -- expected, and found
        again on rerun via the `d3_name` stamp rather than its name.
        `parent=bpy.context.scene.collection` works and is equivalent
        to `parent=None` for visibility (confirmed against real bpy),
        except that the lookup is scoped to the scene root's direct
        children rather than every collection in the file."""
        import bpy

        if parent is None:
            for c in self.collections:
                if self.name_of(c) == name:
                    return c
        else:
            found = self._find_child_collection(parent, name)
            if found is not None:
                return found
        coll = bpy.data.collections.new(name)
        coll[self.COLLECTION_NAME_PROP] = name
        (parent if parent is not None else bpy.context.scene.collection).children.link(coll)
        self.collections.append(coll)
        if parent is not None:
            self._record_collection_parent(coll, parent)
        return coll

    def creator(self, name, collection, **create_kwargs):
        """Real implementation of Join.join()'s string shorthand -- see
        its docstring. `collection` is required, not defaulted to
        whatever bpy.context.collection happens to currently be: that
        ambient default is Blender's own "Scene Collection" unless a
        script has specifically pointed the active layer collection
        elsewhere first, and an object linked only there is invisible
        to select() (see README/CLAUDE.md's Testing status section for
        the full explanation) -- exactly the kind of silent, invisible
        trap a convenience meant to remove boilerplate shouldn't hand
        you by default.

        `create_kwargs` values can be plain values or `fn(d) -> value`
        callables, evaluated per element as it enters -- the same
        accessor idiom as `Selection.attr()`, since shape parameters
        (radius, segments, ring_count, ...) are the one thing that has
        to be supplied at creation time in real bpy: they're baked into
        the mesh's vertex/face data, not settable object properties
        afterward (confirmed: setting `obj['segments'] = 32` on an
        already-created sphere changes nothing about its geometry).
        Genuinely mutable properties -- `location`, `scale`, custom
        props -- stay ordinary `.attr()` calls after the join, same as
        always; `.attr('scale', lambda el, d, i: (d['radius'],) * 3)`
        is the correct way to vary a created primitive's *apparent*
        size per datum without needing per-datum creation kwargs at
        all."""
        import bpy

        try:
            op_name, defaults = _PRIMITIVE_OPS[name]
        except KeyError:
            raise ValueError(
                f"no primitive creator named {name!r} -- available: "
                f"{sorted(_PRIMITIVE_OPS)}. For anything else (a light, a "
                "camera, geometry from databpy/nodebpy, ...), pass your own "
                "enter=... callable instead (see CLAUDE.md)."
            )
        op = getattr(bpy.ops.mesh, op_name)
        params = {**defaults, **create_kwargs}

        def make(d):
            kwargs = {k: (v(d) if callable(v) else v) for k, v in params.items()}
            op(**kwargs)
            obj = bpy.context.active_object
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            collection.objects.link(obj)
            self.objects.append(obj)
            return obj

        return make

    def create_line_mesh(self, collection, name, segments):
        """Same contract as SceneAdapter.create_line_mesh(), except it
        builds a real bpy mesh (bpy.data.meshes.new() + from_pydata())
        instead of the duck-typed stand-in."""
        import bpy

        vertices, edges = _segments_to_vertices_edges(segments)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, edges, [])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        self.objects.append(obj)
        return obj

    def point_attr(self, el, name):
        """Same contract as SceneAdapter.point_attr(), but bulk
        (`foreach_get`) instead of a per-vertex Python loop -- measured
        ~100x faster at real point counts (see tests/blender/), which
        matters more here than anywhere else in this file: the entire
        reason to reach for vertices instead of objects is scale, so a
        naive per-item loop would quietly defeat its own purpose."""
        mesh = el.data
        n = len(mesh.vertices)
        if name == 'position':
            flat = [0.0] * (n * 3)
            mesh.vertices.foreach_get('co', flat)
            return [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
        attr = mesh.attributes[name]
        arity, field = _POINT_ATTR_SHAPE[attr.data_type]
        flat = [0] * (n * arity)
        attr.data.foreach_get(field, flat)
        if arity == 1:
            return flat
        return [tuple(flat[i:i + arity]) for i in range(0, len(flat), arity)]

    def set_point_attr(self, el, name, values):
        """Bulk (`foreach_set`) counterpart to point_attr() above -- same
        never-resizes contract as SceneAdapter.set_point_attr()."""
        mesh = el.data
        values = list(values)
        _check_point_count(self, el, name, len(mesh.vertices), values)
        if name == 'position':
            mesh.vertices.foreach_set('co', [c for co in values for c in co])
            mesh.update()
            return
        if name in mesh.attributes:
            attr = mesh.attributes[name]
        else:
            attr = mesh.attributes.new(
                name=name, type=_infer_point_attr_type(values[0]), domain='POINT')
        arity, field = _POINT_ATTR_SHAPE[attr.data_type]
        flat = values if arity == 1 else [c for v in values for c in v]
        attr.data.foreach_set(field, flat)
        mesh.update()


def get_adapter():
    """Build an adapter snapshotting the current bpy.data. Cheap enough to
    call at the top of every script/operator invocation."""
    import bpy

    return LiveBlenderAdapter(objects=bpy.data.objects, collections=bpy.data.collections)


def live_point_data(adapter, el, **channels):
    """Wire points.point_data(adapter, el, frame, **channels) to Blender's
    own frame-change signal, so scrubbing or playing the timeline
    recomputes and rewrites `el`'s point-attribute channels live -- the
    point_data() equivalent of writing real keyframes with
    Selection.keyframe(), from the caller's point of view. Nothing is
    actually stored, though: unlike keyframes, every frame change just
    re-runs your channel functions fresh (see points.point_data's
    docstring for why point_data can't keyframe in the first place --
    per-vertex custom attributes can't be keyframed through bpy's RNA
    system at all, and per-vertex position keyframing doesn't scale).

    Applies once immediately at the current frame (so the very first
    view already reflects your formula, not just the mesh's raw rest
    shape -- frame_change_pre only fires on an actual frame *change*),
    then again on every frame_change_pre.

    Safe to call again for the same `el` -- e.g. rerunning your setup
    script while iterating in Blender's Scripting workspace. Any handler
    already registered for this exact object is found and replaced
    first, tagged by name, so handlers don't silently pile up (each
    holding an increasingly stale closure) across reruns -- the same
    rerun-safety concern Join's d3_key stamping exists for, applied to
    handler lifecycle instead of object identity. Replaces the whole
    channel set for that object; it doesn't merge with a previous call's
    channels.

    Returns a zero-argument `stop()` -- call it to remove the live
    binding (e.g. before deleting `el`, so the handler doesn't outlive
    the object it's for).

    Confirmed against real bpy: frame_change_pre fires reliably on
    scene.frame_set(), even headless, and correctly recomputed values on
    every call tested. Not separately verified: real interactive
    scrubbing/Play in a windowed Blender session is a related but
    distinct claim from "scene.frame_set() triggers the handler" -- see
    CLAUDE.md's Testing status section on that distinction generally."""
    import bpy

    name = adapter.name_of(el)

    def handler(scene, depsgraph=None):
        point_data(adapter, el, scene.frame_current, **channels)

    handler._d3blender_live_point_data_for = name

    for stale in [h for h in bpy.app.handlers.frame_change_pre
                  if getattr(h, '_d3blender_live_point_data_for', None) == name]:
        bpy.app.handlers.frame_change_pre.remove(stale)
    bpy.app.handlers.frame_change_pre.append(handler)

    point_data(adapter, el, bpy.context.scene.frame_current, **channels)

    def stop():
        if handler in bpy.app.handlers.frame_change_pre:
            bpy.app.handlers.frame_change_pre.remove(handler)

    return stop
