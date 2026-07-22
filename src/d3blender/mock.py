"""A tiny fake scene mimicking bpy's shape closely enough to test the
selector engine and Selection without Blender installed.

`new_scene()` and `spawn()` are demo/test scaffolding, not part of the
selector engine: every example script needs to (1) build an adapter with
one collection and (2) turn a data point into a linked object, and that
linking dance (append to the collection, set `users_collection`, register
with the adapter) was getting hand-rolled identically in every one. Real
Blender usage doesn't need `spawn()` -- object creation there goes through
`bpy.ops`/`bpy.data.objects.new()`, which is a different shape entirely."""

from .adapter import SceneAdapter


class MockModifier:
    def __init__(self, type_):
        self.type = type_


class MockMaterial:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'<Material {self.name}>'


class MockMaterialSlot:
    """Mirrors bpy's MaterialSlot -- a slot can be empty (`.material is
    None`), and an object can have several. Real bpy's `active_material`
    is a separate, direct shortcut attribute, not derived from
    `material_slots` -- mirrored the same way here."""

    def __init__(self, material=None):
        self.material = material


_OBJECT_REAL_ATTRS = {'name', 'type', 'parent', 'selected', 'hidden',
                       'modifiers', 'users_collection', '_props',
                       'location', 'scale', 'rotation_euler', '_keyframes',
                       'active_material', 'material_slots'}


class MockObject:
    """Deliberately strict: like a real bpy ID datablock, setting anything
    that isn't a known bl_rna-ish property raises AttributeError, forcing
    callers through __setitem__ (custom properties) instead -- the same
    fallback path SceneAdapter.set_attr relies on against real Blender."""

    def __init__(self, name, type_='MESH', parent=None, **props):
        object.__setattr__(self, '_props', dict(props))
        object.__setattr__(self, '_keyframes', [])
        self.name = name
        self.type = type_
        self.parent = parent
        self.selected = False
        self.hidden = False
        self.modifiers = []
        self.active_material = None
        self.material_slots = []
        self.location = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.rotation_euler = (0.0, 0.0, 0.0)

    def __setattr__(self, key, value):
        if key not in _OBJECT_REAL_ATTRS:
            raise AttributeError(f'{key!r} is not a real property; use item assignment')
        object.__setattr__(self, key, value)

    def keyframe_insert(self, data_path, frame):
        """Mirrors bpy's obj.keyframe_insert(data_path=..., frame=...);
        records (frame, path, value) since there's no real timeline here."""
        self._keyframes.append((frame, data_path, getattr(self, data_path)))

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __setitem__(self, key, value):
        self._props[key] = value

    def __getitem__(self, key):
        return self._props[key]

    def __repr__(self):
        return f'<Object {self.name}>'


class MockCollection:
    def __init__(self, name):
        self.name = name
        self.objects = []
        self.children = []
        self._props = {}

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __setitem__(self, key, value):
        self._props[key] = value

    def __repr__(self):
        return f'<Collection {self.name}>'


def new_scene(collection_name='Chart'):
    """A fresh adapter with one top-level collection -- the usual starting
    point for an example or test. Returns (adapter, collection)."""
    collection = MockCollection(collection_name)
    adapter = SceneAdapter(objects=[], collections=[collection])
    return adapter, collection


def spawn(adapter, collection, name, type_='MESH', **props):
    """Create a MockObject, link it into `collection`, and register it
    with `adapter` -- the one new object per data point that .join()'s
    `enter` callback needs to produce."""
    obj = MockObject(name, type_, **props)
    collection.objects.append(obj)
    obj.users_collection = (collection,)
    adapter.objects.append(obj)
    return obj
