import os
import requests

from typing import Optional

from .common import create_changeset_creation_xml


def get_changeset_meta(changeset_id) -> Optional[str]:
    osm_base_url = os.environ.get('OSM_BASE_URL')
    meta_url = f'{osm_base_url}/api/0.6/changeset/{changeset_id}'
    response = requests.get(meta_url)
    status_code = response.status_code
    if status_code == 404:
        return None
    if status_code != 200:
        raise Exception(f'Status code {status_code} while getting changeset')
    return response.text


def get_changeset_data(changeset_id) -> str:
    osm_base_url = os.environ.get('OSM_BASE_URL')
    if not osm_base_url:
        raise Exception('OSM_BASE_URL env not set')
    meta_url = f'{osm_base_url}/api/0.6/changeset/{changeset_id}/download'
    response = requests.get(meta_url)
    status_code = response.status_code
    if status_code != 200:
        raise Exception(f'Status code {status_code} while getting changeset')
    return response.text


def create_changeset(comment: str, version: str) -> int:
    changeset_xml = create_changeset_creation_xml(comment, version)
    changeset_id = 11111
    return changeset_id


def upload_changeset(changeset_id: int, changeset_data: dict) -> bool:
    return True
