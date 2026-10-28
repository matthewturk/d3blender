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


class MockGNInputValue:
    """Mirrors Blender 5.2+'s `modifier.properties.inputs[identifier]` --
    an RNA property wrapper exposing a Geometry Nodes input's actual
    value through `.value`, not the plain-idprop bracket access
    (`modifier[identifier]`) that pre-5.2 Blender used and that now
    raises "id properties not supported for this type" (see
    adapter.py's _gn_input_get/_gn_input_set). Real bpy also has a
    second shape for vector-like sockets -- an IDPropertyGroup needing
    `["value"]` instead -- not modeled here since nothing exercises it
    yet; add a dict-like variant alongside this one if a test needs it,
    following the same `hasattr(holder, 'value')` duck-typed check
    adapter.py already does."""

    def __init__(self, value=None):
        self.value = value

    def __repr__(self):
        return f'<GNInputValue {self.value!r}>'


class MockModifierProperties:
    """Mirrors `modifier.properties` -- just enough to hold `.inputs`,
    the dict Blender 5.2+ actually stores Geometry Nodes input values in
    (see MockGNInputValue). Keyed by identifier ("Input_2"), same as the
    real `items_tree`-derived key."""

    def __init__(self):
        self.inputs = {}


class MockModifier:
    """Real bpy modifiers are addressable by name (auto-uniquified with
    `.001` suffixes, exactly like object/collection names), so `.name`
    defaults to `type_` rather than being omitted. `node_group` is only
    meaningful for `type_='NODES'` (Geometry Nodes) modifiers; a plain
    modifier just leaves it None and gets/sets ordinary attributes
    (`.width`, `.levels`, ...) the normal Python way -- no `__setattr__`
    restriction here, unlike MockObject. `.properties.inputs` holds GN
    input values (see MockModifierProperties); `_props`/`__getitem__`/
    `__setitem__` remain for ordinary custom properties, unrelated to
    Geometry Nodes."""

    def __init__(self, type_, name=None, node_group=None, **props):
        self.type = type_
        self.name = name or type_
        self.node_group = node_group
        self._props = dict(props)
        self.properties = MockModifierProperties()

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __setitem__(self, key, value):
        self._props[key] = value

    def __getitem__(self, key):
        return self._props[key]

    def __repr__(self):
        return f'<Modifier {self.name!r} type={self.type!r}>'


class MockModifierCollection(list):
    """Mirrors bpy's modifiers collection: plain list iteration/indexing,
    plus name-based lookup (`.get(name)`, `['name']`) -- needed since
    path-based attribute access (adapter.get_attr/set_attr) resolves a
    modifier by name, the same way a collection is resolved by name."""

    def get(self, name, default=None):
        for m in self:
            if m.name == name:
                return m
        return default

    def __getitem__(self, key):
        if isinstance(key, str):
            for m in self:
                if m.name == key:
                    return m
            raise KeyError(key)
        return super().__getitem__(key)


class MockNodeGroupInterfaceItem:
    """One row of a Geometry Nodes group's interface (Blender 4.0+/5.x
    shape: `node_group.interface.items_tree`) -- `name` is the
    human-readable socket name, `identifier` the underlying ID-property
    key (`modifier[identifier]`) that actually stores the value."""

    def __init__(self, name, identifier, in_out='INPUT'):
        self.name = name
        self.identifier = identifier
        self.in_out = in_out


class MockNodeGroupInterface:
    def __init__(self, items=()):
        self.items_tree = list(items)


class MockNodeGroup:
    def __init__(self, items=()):
        self.interface = MockNodeGroupInterface(items)


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


class MockVertex:
    """Mirrors bpy's MeshVertex, scoped to the one field d3blender's
    point-attribute machinery touches: `.co`."""

    def __init__(self, co=(0.0, 0.0, 0.0)):
        self.co = tuple(co)

    def __repr__(self):
        return f'<MockVertex co={self.co!r}>'


class MockPointAttributeItem:
    """One vertex's worth of a point-domain attribute -- exposes whichever
    field name (.value/.vector/.color) its attribute's data_type calls
    for, mirroring the type-dependent shape adapter.py's _POINT_ATTR_SHAPE
    already expects from real bpy (see there for why: FLOAT/INT/BOOLEAN
    -> .value, FLOAT_VECTOR -> .vector, FLOAT_COLOR -> .color)."""

    def __init__(self, field, value):
        setattr(self, field, value)


class MockPointAttribute:
    """Mirrors one entry of bpy's mesh.attributes -- a typed, named,
    POINT-domain array, one MockPointAttributeItem per vertex."""

    def __init__(self, name, data_type, size):
        from .adapter import _POINT_ATTR_SHAPE
        self.name = name
        self.data_type = data_type
        self.domain = 'POINT'
        arity, field = _POINT_ATTR_SHAPE[data_type]
        default = 0.0 if arity == 1 else (0.0,) * arity
        self.data = [MockPointAttributeItem(field, default) for _ in range(size)]


class MockAttributeCollection(dict):
    """Mirrors mesh.attributes -- name-addressable, `in`-checkable, raises
    KeyError on a missing name, exactly like a plain dict already does.
    `.new(name=, type=, domain=)` is the one bit of real-bpy-shaped
    behavior on top of that."""

    def __init__(self, size):
        super().__init__()
        self._size = size

    def new(self, name, type, domain='POINT'):
        attr = MockPointAttribute(name, type, self._size)
        self[name] = attr
        return attr


class MockMesh:
    """Mirrors bpy.types.Mesh, scoped to exactly what d3blender's
    point-attribute machinery touches: `.vertices` (plain list of
    MockVertex) and `.attributes` (named per-vertex data, see
    MockAttributeCollection). `.update()` is a no-op -- there's no real
    depsgraph here to notify."""

    def __init__(self, vertices):
        self.vertices = [MockVertex(co) for co in vertices]
        self.attributes = MockAttributeCollection(len(self.vertices))

    def update(self):
        pass


_OBJECT_REAL_ATTRS = {'name', 'type', 'parent', 'selected', 'hidden',
                       'modifiers', 'users_collection', '_props',
                       'location', 'scale', 'rotation_euler', '_keyframes',
                       'active_material', 'material_slots', 'data'}


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
        self.modifiers = MockModifierCollection()
        self.active_material = None
        self.material_slots = []
        self.location = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.data = None  # a MockMesh, for point_attr/set_point_attr -- see spawn_points()

    def __setattr__(self, key, value):
        if key not in _OBJECT_REAL_ATTRS:
            raise AttributeError(f'{key!r} is not a real property; use item assignment')
        object.__setattr__(self, key, value)

    def keyframe_insert(self, data_path, frame):
        """Mirrors bpy's obj.keyframe_insert(data_path=..., frame=...);
        records (frame, path, value) since there's no real timeline here.
        Strict like real bpy: a bare custom-property name raises
        TypeError ("property not found"); custom props must be addressed
        as an ID-property path, '["hp"]'."""
        if data_path.startswith('["') and data_path.endswith('"]'):
            key = data_path[2:-2].replace('\\"', '"').replace('\\\\', '\\')
            if key not in self._props:
                raise TypeError(f'keyframe_insert() property {data_path!r} not found')
            self._keyframes.append((frame, data_path, self._props[key]))
            return
        if data_path not in _OBJECT_REAL_ATTRS:
            raise TypeError(f'bpy_struct.keyframe_insert() property "{data_path}" not found')
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


def spawn_points(adapter, collection, name, vertices, **props):
    """Like spawn(), but gives the object a MockMesh sized to `vertices`
    (a list of (x, y, z) local-space coordinates) -- the one-object-with-
    many-vertices analogue of spawn(), for point_attr/set_point_attr and
    point_data() instead of one object per datum. Mirrors real bpy's
    `mesh.from_pydata(vertices, [], [])` + `objects.new(name, mesh)`
    shape closely enough to exercise the same adapter code either way."""
    obj = spawn(adapter, collection, name, **props)
    obj.data = MockMesh(vertices)
    return obj
