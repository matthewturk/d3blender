"""
scene_doc.py — turns the current scene into two small BeautifulSoup
documents (one per axis) so a real, mature CSS engine (soupsieve, via
BeautifulSoup) does all of the structural matching: type, .class, #id,
[attr=value], and the ' '/'>' combinators. We only write the axis-selection
and the bits CSS genuinely can't express (numeric attribute comparisons,
domain pseudo-classes) — see query.py.

Two documents because Blender has two real hierarchies and CSS only has one:
  - collection doc: mirrors containment (`.users_collection`, `.children`)
  - parent doc:     mirrors transform parenting (`obj.parent`)

An object that's linked into multiple collections legitimately appears
under multiple tags in the collection doc — soupsieve will find both, and
we de-duplicate back to the same real object afterwards via ref_map.
"""

from bs4 import BeautifulSoup


def _new_tag(soup, el, adapter, ref_map, counter):
    ref_id = f'r{next(counter)}'
    ref_map[ref_id] = el
    tag = soup.new_tag(adapter.type_of(el))
    tag['id'] = adapter.name_of(el)
    tag['data-ref'] = ref_id
    classes = adapter.classes_of(el)
    if classes:
        tag['class'] = ' '.join(sorted(classes))
    material = adapter.material_of(el)
    if material:
        tag['material'] = material
    for key, value in adapter.simple_attrs(el).items():
        # only plain scalars are meaningful as CSS attribute text
        # (a custom prop literally named "material" would win here,
        # overriding the synthetic active-material attribute above)
        if isinstance(value, (str, int, float, bool)):
            tag[key] = str(value)
    return tag


def build_collection_doc(adapter):
    """Nested by containment: collections hold sub-collections and objects."""
    soup = BeautifulSoup('<scene></scene>', 'html.parser')
    ref_map = {}
    counter = iter(range(10 ** 9))
    tag_by_collection = {}

    def build_collection_tag(coll):
        if id(coll) in tag_by_collection:
            return tag_by_collection[id(coll)]
        tag = _new_tag(soup, coll, adapter, ref_map, counter)
        tag_by_collection[id(coll)] = tag
        for child_coll in adapter.sub_collections(coll):
            tag.append(build_collection_tag(child_coll))
        for obj in adapter.collection_objects(coll):
            tag.append(_new_tag(soup, obj, adapter, ref_map, counter))
        return tag

    for coll in adapter.top_level_collections():
        soup.scene.append(build_collection_tag(coll))
    for obj in adapter.objects_without_collection():
        soup.scene.append(_new_tag(soup, obj, adapter, ref_map, counter))

    return soup, ref_map


def build_parent_doc(adapter):
    """Nested by transform parenting: objects only, root = no parent."""
    soup = BeautifulSoup('<scene></scene>', 'html.parser')
    ref_map = {}
    counter = iter(range(10 ** 9))
    children_index = adapter.build_parent_children_index()

    def build_object_tag(obj):
        tag = _new_tag(soup, obj, adapter, ref_map, counter)
        for child in children_index.get(id(obj), []):
            tag.append(build_object_tag(child))
        return tag

    for obj in adapter.objects:
        if adapter.parent_of(obj) is None:
            soup.scene.append(build_object_tag(obj))

    return soup, ref_map
