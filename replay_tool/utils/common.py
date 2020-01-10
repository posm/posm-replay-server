import os
import json
from datetime import datetime

from typing import Any, List, Optional, Dict
from mypy_extensions import TypedDict
from .osmium_handlers import AOIHandler, OSMElementsTracker


class FilteredElements(TypedDict):
    referenced: Any
    deleted: Any
    modified: Any
    referring: Any


class AOIInfo(TypedDict):
    bbox: List[float]
    description: str


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
    original_aoi_name = os.environ.get('ORIGINAL_AOI_FILE_NAME')
    if not original_aoi_name:
        raise Exception('ORIGINAL_AOI_FILE_NAME should be defined in the env')
    return os.path.join(aoi_path, original_aoi_name)


def create_deleted_element(eid):
    return {
        'id': eid,
        'deleted': True,
    }


def get_overpass_query(s, w, n, e) -> str:
    return f'(node({s},{w},{n},{e});<;>>;>;);out meta;'


def filter_elements_from_aoi_handler(tracker: OSMElementsTracker, aoi_handler: AOIHandler) -> FilteredElements:
    """This function is used inside reducer to filter osm elements"""
    elements: FilteredElements = {
        'referenced': {'nodes': {}, 'ways': {}, 'relations': {}},
        'modified': {'nodes': {}, 'ways': {}, 'relations': {}},
        'deleted': {'nodes': {}, 'ways': {}, 'relations': {}},
        'referring': {'ways': {}, 'relations': {}}
    }
    for nid in tracker.deleted_elements['nodes']:
        elements['deleted']['nodes'][nid] = aoi_handler.nodes.get(nid) or create_deleted_element(nid)
    for nid in tracker.referenced_elements['nodes']:
        elements['referenced']['nodes'][nid] = aoi_handler.nodes.get(nid) or create_deleted_element(nid)
    for nid in tracker.modified_elements['nodes']:
        elements['modified']['nodes'][nid] = aoi_handler.nodes.get(nid) or create_deleted_element(nid)

    for wid in tracker.deleted_elements['ways']:
        elements['deleted']['ways'][wid] = aoi_handler.ways.get(wid) or create_deleted_element(wid)
    for wid in tracker.referenced_elements['ways']:
        elements['referenced']['ways'][wid] = aoi_handler.ways.get(wid) or create_deleted_element(wid)
    for wid in tracker.modified_elements['ways']:
        elements['modified']['ways'][wid] = aoi_handler.ways.get(wid) or create_deleted_element(wid)

    for rid in tracker.deleted_elements['relations']:
        elements['deleted']['relations'][rid] = aoi_handler.relations.get(rid) or create_deleted_element(rid)
    for rid in tracker.referenced_elements['relations']:
        elements['referenced']['relations'][rid] = aoi_handler.relations.get(rid) or create_deleted_element(rid)
    for rid in tracker.modified_elements['relations']:
        elements['modified']['relations'][rid] = aoi_handler.relations.get(rid) or create_deleted_element(rid)
    return elements


def create_changeset_creation_xml(comment: str, tool_version: str = '1.1') -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
        <osm version="0.6" generator="POSM Replay Tool v{tool_version}">
        <changeset>
            <tag k="comment" v="{comment}" />
        </changeset>
    </osm>'''


def transform_tags_to_dict(tags):
    if isinstance(tags, dict):
        return tags
    elif isinstance(tags, list):
        return {x['k']: x['v'] for x in tags}
    else:
        raise Exception('Invalid tags')


def get_osm_elems_diff(a: dict, b: dict) -> dict:
    tagsa = transform_tags_to_dict(a.get('tags', []))
    tagsb = transform_tags_to_dict(b.get('tags', []))
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
            member['type'] = 'node'
            member['ref'] = new_nodes_ids_map.get(member['ref'], member['ref'])
        elif member['type'] == 'w':
            member['type'] = 'way'
            member['ref'] = new_ways_ids_map.get(member['ref'], member['ref'])
        elif member['type'] == 'r':
            member['type'] = 'relation'
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
