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


def test_select_wraps_single_element_directly(scene):
    sword = select(scene, '#Sword').elements[0]
    assert names(select(scene, sword)) == ['Sword']


def test_select_wraps_element_list_directly(scene):
    sword = select(scene, '#Sword').elements[0]
    shield = select(scene, '#Shield').elements[0]
    assert names(select(scene, [sword, shield])) == ['Shield', 'Sword']


def test_select_by_dotted_name_is_not_valid_css(scene):
    # A `#name` selector goes through CSS, where "." starts a class --
    # names like Blender's own auto-suffixed "Cube.001" were never valid
    # here. Re-wrap the element directly instead (see test above).
    import pytest
    from d3blender.mock import MockObject

    dotted = MockObject('Sword.001', 'MESH')
    scene.objects.append(dotted)
    with pytest.raises(Exception):
        select(scene, f'#{dotted.name}')
    assert names(select(scene, dotted)) == ['Sword.001']
