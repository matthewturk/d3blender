"""A tiny fake scene mimicking bpy's shape closely enough to test the
selector engine and Selection without Blender installed."""


class MockModifier:
    def __init__(self, type_):
        self.type = type_


_OBJECT_REAL_ATTRS = {'name', 'type', 'parent', 'selected', 'hidden',
                       'modifiers', 'users_collection', '_props',
                       'location', 'scale', 'rotation_euler', '_keyframes'}


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
