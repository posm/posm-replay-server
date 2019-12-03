import os
from functools import reduce

from replay_tool.serializers import NodeSerializer, WaySerializer, RelationSerializer


def get_aoi_path() -> str:
    aoi_root = os.environ.get('AOI_ROOT')
    aoi_name = os.environ.get('AOI_NAME')
    if not aoi_root or not aoi_name:
        raise Exception('AOI_ROOT and AOI_NAME must both be defined in env')
    return os.path.join(aoi_root, aoi_name)


def get_local_aoi_path() -> str:
    return os.path.join(get_aoi_path(), 'local_aoi.osm')


def get_current_aoi_path() -> str:
    return os.path.join(get_aoi_path(), 'current_aoi.osm')


def get_overpass_query(s, w, n, e) -> str:
    return f'(node({s},{w},{n},{e});<;>>;>;);out meta;'


def filter_elements_from_tracker(item, tracker):
    """This function is used inside reducer to filter item[nodes/ways/relations]"""
    def filter_func(acc: dict, id_elem: (int, object)):
        # id_elem is from local/upstream aoi
        eid, elem = id_elem
        if eid in tracker.added_elements[item]:
            acc['added'][eid] = elem
        elif eid in tracker.modified_elements['elems']:
            acc['modified'][eid] = elem
        elif eid in tracker.deleted_elements['elems']:
            acc['deleted'][eid] = elem
        if eid in tracker.referenced_elements['elems']:
            acc['referenced'][eid] = elem
        return acc
    return filter_func


def filter_elements_from_aoi_handler(tracker, aoi_handler):
    """This function is used inside reducer to filter osm elements"""
    elements: dict = {}

    elements['nodes'] = reduce(
        filter_elements_from_tracker('nodes', tracker),
        aoi_handler.nodes,
        {}
    )
    elements['ways'] = reduce(
        filter_elements_from_tracker('ways', tracker),
        aoi_handler.ways,
        {}
    )
    elements['relations'] = reduce(
        filter_elements_from_tracker('relations', tracker),
        aoi_handler.relations,
        {}
    )
    return elements


def pop_irrlevant_osm_attrs(elem: dict):
    irrelevant_attrs = ['timestamp', 'uid', 'user', 'location']
    return {
        k: v
        for k, v in elem.items()
        if k not in irrelevant_attrs
    }


def do_elements_conflict(element1_serialized: dict, element2_serialized: dict) -> bool:
    """The elements element1 and element2 represent the same element(same id) and are from
    local and upstream db respectively
    """
    if element1_serialized['visible'] != element2_serialized['visible']:
        return True

    # pop irrelevant keys and attributes
    element1_serialized = pop_irrlevant_osm_attrs(element1_serialized)
    element2_serialized = pop_irrlevant_osm_attrs(element2_serialized)

    e1_tags = element1_serialized.pop('tags', [])
    e2_tags = element2_serialized.pop('tags', [])

    e1_nodes = element1_serialized.pop('nodes', [])
    e2_nodes = element2_serialized.pop('nodes', [])

    e1_members = element1_serialized.pop('members', [])
    e2_members = element2_serialized.pop('members', [])

    # Check basic attributes
    if element1_serialized != element2_serialized:
        return True

    # Check tags
    if len(e1_tags) != len(e2_tags):
        return True
    n1_tags_keyvals = {x['k']: x['v'] for x in e1_tags}
    n2_tags_keyvals = {x['k']: x['v'] for x in e2_tags}

    if n1_tags_keyvals != n2_tags_keyvals:
        return True

    # Check nodes(in case of way)
    # NOTE: In the case of nodes, just checking if objects are equal is enough
    # because order of noderefs matters for way
    if e1_nodes != e2_nodes:
        return True

    # Check members(in case of members)
    if len(e1_members) != len(e2_members):
        return True
    e1_members_keyvals = {x['k']: x['v'] for x in e1_members}
    e2_members_keyvals = {x['k']: x['v'] for x in e2_members}

    if e1_members_keyvals != e2_members_keyvals:
        return True


def filter_conflicting_pairs(local_referenced_elements, aoi_referenced_elements, Serializer):
    """
    Returns [(serialized_local_element1, seriaalized_aoi_element1), ...] of conflicting elements
    """
    conflicting_elements = []
    for l_nid, local_element in local_referenced_elements.items():
        # NOTE: Assumption that l_nid is always present in aoi_referenced_elements
        # which is a very valid assumption
        aoi_element = aoi_referenced_elements[l_nid]
        serialized_aoi_element = Serializer(aoi_element).data
        serialized_local_element = Serializer(local_element).data
        if do_elements_conflict(serialized_local_element, serialized_aoi_element):
            conflicting_elements.append((serialized_local_element, serialized_aoi_element))
    return conflicting_elements


def get_conflicting_elements(local_referenced_elements, aoi_referenced_elements):
    return {
        'nodes': filter_conflicting_pairs(
            local_referenced_elements['nodes'],
            aoi_referenced_elements['nodes'],
            NodeSerializer,
        ),
        'ways': filter_conflicting_pairs(
            local_referenced_elements['ways'],
            aoi_referenced_elements['ways'],
            WaySerializer,
        ),
        'relations': filter_conflicting_pairs(
            local_referenced_elements['relations'],
            aoi_referenced_elements['relations'],
            RelationSerializer,
        ),
    }
