import os
import json
from copy import deepcopy
from datetime import datetime

from typing import Any, Tuple, List, Optional, TypeVar, Dict
from mypy_extensions import TypedDict
from .osmium_handlers import AOIHandler, OSMElementsTracker


T = TypeVar('T')


class FilteredElements(TypedDict):
    referenced: Any
    deleted: Any
    modified: Any


class AOIInfo(TypedDict):
    bbox: List[float]
    description: str


class ConflictingElements(TypedDict):
    nodes: List[Tuple[object, object]]
    ways: List[Tuple[object, object]]
    relations: List[Tuple[object, object]]


def get_aoi_name(exception_if_not_set=False) -> Optional[str]:
    aoi_name = os.environ.get('AOI_NAME')
    if exception_if_not_set and not aoi_name:
        raise Exception('AOI_ROOT and AOI_NAME must both be defined in env')
    return aoi_name


def get_aoi_created_datetime() -> datetime:
    aoi_path = get_aoi_path()
    return datetime.utcfromtimestamp(os.path.getctime(aoi_path))


def get_aoi_path() -> str:
    aoi_root = os.environ.get('AOI_ROOT')
    aoi_name = get_aoi_name()
    if not aoi_root or not aoi_name:
        raise Exception('AOI_ROOT and AOI_NAME must both be defined in env')
    return os.path.join(aoi_root, aoi_name)


def get_current_aoi_info() -> AOIInfo:
    aoi_path = get_aoi_path()
    manifest_path = os.path.join(aoi_path, 'manifest.json')

    # TODO: Check if manifest file exists
    with open(manifest_path) as f:
        manifest = json.load(f)
        bbox = manifest['bbox']
        description = manifest['description']
        # bbox is of the form [w, s, e, n]
        return {'bbox': bbox, 'description': description}


def get_local_aoi_path() -> str:
    return os.path.join(get_aoi_path(), 'local_aoi.osm')


def get_current_aoi_path() -> str:
    return os.path.join(get_aoi_path(), 'current_aoi.osm')


def get_original_aoi_path() -> str:
    aoi_path = get_aoi_path()
    original_aoi_name = os.environ.get('ORIGINAL_AOI_NAME')
    if not original_aoi_name:
        raise Exception('ORIGINAL_AOI_NAME should be defined in the env')
    return os.path.join(aoi_path, original_aoi_name)


def get_overpass_query(s, w, n, e) -> str:
    return f'(node({s},{w},{n},{e});<;>>;>;);out meta;'


def filter_elements_from_aoi_handler(tracker: OSMElementsTracker, aoi_handler: AOIHandler) -> FilteredElements:
    """This function is used inside reducer to filter osm elements"""
    elements: FilteredElements = {
        'referenced': {'nodes': {}, 'ways': {}, 'relations': {}},
        'modified': {'nodes': {}, 'ways': {}, 'relations': {}},
        'deleted': {'nodes': {}, 'ways': {}, 'relations': {}},
    }
    for nid in tracker.deleted_elements['nodes']:
        elements['deleted']['nodes'][nid] = aoi_handler.nodes[nid]
    for nid in tracker.referenced_elements['nodes']:
        elements['referenced']['nodes'][nid] = aoi_handler.nodes[nid]
    for nid in tracker.modified_elements['nodes']:
        elements['modified']['nodes'][nid] = aoi_handler.nodes[nid]

    for nid in tracker.deleted_elements['ways']:
        elements['deleted']['ways'][nid] = aoi_handler.ways[nid]
    for nid in tracker.referenced_elements['ways']:
        elements['referenced']['ways'][nid] = aoi_handler.ways[nid]
    for nid in tracker.modified_elements['ways']:
        elements['modified']['ways'][nid] = aoi_handler.ways[nid]

    for nid in tracker.deleted_elements['relations']:
        elements['deleted']['relations'][nid] = aoi_handler.relations[nid]
    for nid in tracker.referenced_elements['relations']:
        elements['referenced']['relations'][nid] = aoi_handler.relations[nid]
    for nid in tracker.modified_elements['relations']:
        elements['modified']['relations'][nid] = aoi_handler.relations[nid]
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

    return e1_members_keyvals != e2_members_keyvals


def filter_conflicting_pairs(local_referenced_elements, aoi_referenced_elements):
    """
    Returns [(serialized_local_element1, seriaalized_aoi_element1), ...] of conflicting elements
    """
    conflicting_elements = []
    for l_nid, local_element in local_referenced_elements.items():
        # NOTE: Assumption that l_nid is always present in aoi_referenced_elements
        # which is a very valid assumption
        aoi_element = aoi_referenced_elements.get(l_nid)
        if not aoi_element:
            continue
        if do_elements_conflict(deepcopy(aoi_element), deepcopy(local_element)):
            conflicting_elements.append(local_element['id'])
    return conflicting_elements


def get_conflicting_elements(
    local_referenced_elements, aoi_referenced_elements, version_handler
) -> ConflictingElements:
    # Filter elements that have been changed in upstream, ignore other
    upstream_changed_nodes = {
        k: v for k, v in aoi_referenced_elements['nodes'].items()
        if v['version'] > version_handler.nodes_versions[v['id']]
    }

    upstream_changed_ways = {
        k: v for k, v in aoi_referenced_elements['ways'].items()
        if v['version'] > version_handler.ways_versions[v['id']]
    }
    upstream_changed_relations = {
        k: v for k, v in aoi_referenced_elements['relations'].items()
        if v['version'] > version_handler.relations_versions[v['id']]
    }
    conflicting_elems: ConflictingElements = {
        'nodes': filter_conflicting_pairs(
            local_referenced_elements['nodes'],
            upstream_changed_nodes,
        ),
        'ways': filter_conflicting_pairs(
            local_referenced_elements['ways'],
            upstream_changed_ways,
        ),
        'relations': filter_conflicting_pairs(
            local_referenced_elements['relations'],
            upstream_changed_relations,
        ),
    }
    return conflicting_elems


def create_changeset_creation_xml(comment: str, tool_version: str = '1.1') -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
        <osm version="0.6" generator="POSM Replay Tool v{tool_version}">
        <changeset>
            <tag k="comment" v="{comment}" />
        </changeset>
    </osm>'''


def get_osm_elems_diff(a: dict, b: dict) -> dict:
    tagsa = {x['k']: x['v'] for x in a.get('tags', [])}
    tagsb = {x['k']: x['v'] for x in b.get('tags', [])}
    tags_diff = {k: v for k, v in tagsa.items() if v != tagsb.get(k)}
    tags = [{'k': k, 'v': v} for k, v in tags_diff.items()]
    attrs_diff = {k: v for k, v in a.items() if v != b.get(k) and k != 'tags'}

    return {**attrs_diff, 'tags': tags}


def replace_new_node_data(data: dict, nodes_new_ids_map: Dict[int, int]) -> dict:
    local_id = data['id']
    # This might not be added element, so if id is not in map, just use the existing id
    new_id = nodes_new_ids_map.get(local_id, local_id)
    data['id'] = new_id
    return data


def replace_new_way_data(
    data: dict,
    new_nodes_ids_map: Dict[int, int],
    new_ways_ids_map: Dict[int, int],
) -> dict:
    local_id = data['id']
    # This might not be added element, so if id is not in map, just use the existing id
    new_id = new_ways_ids_map.get(local_id, local_id)
    new_nodes = [
        # Get new id, if not present it is not new id, use the same id value
        {"ref": new_nodes_ids_map.get(x['ref'], x['ref'])}
        for x in data.get('nodes', [])  # nodes won't be present in changeset data if not modified
    ]
    data['id'] = new_id
    data['nodes'] = new_nodes
    return data


def replace_new_relation_data(
    data: dict,
    new_nodes_ids_map: Dict[int, int],
    new_ways_ids_map: Dict[int, int],
    new_relations_ids_map: Dict[int, int],
) -> dict:
    local_id = data['id']
    # This might not be added element, so if id is not in map, just use the existing id
    new_id = new_ways_ids_map.get(local_id, local_id)
    # Change relations and ways ids if new
    for member in data.get('members', []):
        if member['type'] == 'n':
            member['ref'] = new_nodes_ids_map.get(member['ref'], member['ref'])
        elif member['type'] == 'w':
            member['ref'] = new_ways_ids_map.get(member['ref'], member['ref'])
        elif member['type'] == 'r':
            member['ref'] = new_relations_ids_map.get(member['ref'], member['ref'])
        else:
            raise Exception(f'Invalid member type "{member["type"]}".')
    data['id'] = new_id
    return data


def replace_new_element_ids(
    changeset_data: dict,
    new_nodes_ids_map: Dict[int, int],
    new_ways_ids_map: Dict[int, int],
    new_relations_ids_map: Dict[int, int]
) -> dict:
    elemtype = changeset_data['type']

    if elemtype == 'node':
        new_data = replace_new_node_data(changeset_data['data'], new_nodes_ids_map)
    elif elemtype == 'way':
        new_data = replace_new_way_data(changeset_data['data'], new_nodes_ids_map, new_ways_ids_map)
    elif elemtype == 'relation':
        new_data = replace_new_relation_data(
            changeset_data['data'],
            new_nodes_ids_map,
            new_ways_ids_map,
            new_relations_ids_map
        )
    else:
        raise Exception(f'Invalid element type "{elemtype}"')
    changeset_data['data'] = new_data
    return changeset_data
