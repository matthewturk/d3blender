from d3blender import select


def names(sel):
    return sorted(el.name for el in sel)


def test_type_selector(scene):
    assert names(select(scene, 'mesh')) == ['Barrel', 'Shield', 'Sword', 'Sword_Held']


def test_class_selector(scene):
    assert names(select(scene, '.enemy')) == ['Shield', 'Sword']


def test_numeric_attribute_selector(scene):
    assert names(select(scene, '[hp>25]')) == ['Shield', 'Sword', 'Sword_Held']


def test_collection_axis_direct_child(scene):
    assert names(select(scene, '#Weapons > mesh')) == ['Shield', 'Sword']


def test_collection_axis_descendant_reaches_nested_collections(scene):
    # Props is nested inside Characters, so this must reach Barrel too.
    assert names(select(scene, '#Characters mesh')) == ['Barrel', 'Sword_Held']


def test_collection_axis_direct_child_excludes_nested(scene):
    assert names(select(scene, '#Characters > mesh')) == ['Sword_Held']


def test_parent_axis_descendant(scene):
    assert names(select(scene, '#Rig ~ *')) == ['Hand', 'Head', 'Sword_Held']


def test_parent_axis_direct_child(scene):
    assert names(select(scene, '#Rig ~> *')) == ['Hand', 'Head']


def test_pseudo_class(scene):
    assert names(select(scene, ':hidden')) == ['Head']


def test_pseudo_class_with_argument(scene):
    assert names(select(scene, 'mesh:has-modifier(BEVEL)')) == ['Sword']


def test_mixed_axis_raises(scene):
    import pytest
    with pytest.raises(ValueError):
        select(scene, 'Rig ~ Weapons > mesh')
