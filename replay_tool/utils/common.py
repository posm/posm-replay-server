import os
import json
from datetime import datetime

from replay_tool.models import ReplayToolConfig

from typing import Any, List, Optional
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
    config = ReplayToolConfig.load()
    aoi_name = config.aoi_name
    if exception_if_not_set and not aoi_name:
        raise Exception('aoi_root and aoi_name must both be configured')
    return aoi_name


def get_aoi_created_datetime() -> datetime:
    aoi_path = get_aoi_path()
    return datetime.utcfromtimestamp(os.path.getctime(aoi_path))


def get_aoi_path() -> str:
    config = ReplayToolConfig.load()
    aoi_root = config.aoi_root
    aoi_name = get_aoi_name()
    if not aoi_root or not aoi_name:
        raise Exception('aoi_root and aoi_name must both be configured')
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
    config = ReplayToolConfig.load()
    original_aoi_name = config.original_aoi_file_name
    if not original_aoi_name:
        raise Exception('original_aoi_file_name should be configured')
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
