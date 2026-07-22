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

from .adapter import SceneAdapter, _segments_to_vertices_edges


class LiveBlenderAdapter(SceneAdapter):
    """Same as SceneAdapter, except remove() calls the real bpy.data
    removal APIs (which already handle unlinking) instead of the mock's
    manual list surgery, get_or_create_collection() creates a real bpy
    collection and links it into the scene, and create_line_mesh()
    builds a real bpy mesh."""

    def remove(self, el):
        import bpy

        if hasattr(el, 'objects') and hasattr(el, 'children'):
            bpy.data.collections.remove(el)
        else:
            bpy.data.objects.remove(el, do_unlink=True)

    def get_or_create_collection(self, name, parent=None):
        """Same contract as SceneAdapter.get_or_create_collection(),
        except a real bpy.data.collections.new() result also needs
        linking into the scene (or a parent collection) to actually show
        up -- an unlinked collection is an orphan datablock, invisible in
        the outliner/viewport."""
        import bpy

        for c in self.collections:
            if self.name_of(c) == name:
                return c
        coll = bpy.data.collections.new(name)
        (parent if parent is not None else bpy.context.scene.collection).children.link(coll)
        self.collections.append(coll)
        if parent is not None:
            self._collection_parent.setdefault(id(coll), []).append(parent)
        return coll

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


def get_adapter():
    """Build an adapter snapshotting the current bpy.data. Cheap enough to
    call at the top of every script/operator invocation."""
    import bpy

    return LiveBlenderAdapter(objects=bpy.data.objects, collections=bpy.data.collections)
