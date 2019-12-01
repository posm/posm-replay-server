import os
import requests


def get_changeset_meta(changeset_id) -> str:
    osm_base_url = os.environ.get('OSM_BASE_URL', 'http://localhost:3000')
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
