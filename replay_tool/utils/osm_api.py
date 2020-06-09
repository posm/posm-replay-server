import os
import requests

from replay_tool.models import ReplayToolConfig


from typing import Optional


def get_changeset_meta(changeset_id, config: ReplayToolConfig) -> Optional[str]:
    osm_base_url = config.osm_base_url
    meta_url = f'{osm_base_url}/api/0.6/changeset/{changeset_id}'
    response = requests.get(meta_url)
    status_code = response.status_code
    if status_code == 404:
        return None
    if status_code != 200:
        raise Exception(f'Status code {status_code} while getting changeset')
    return response.text


def get_changeset_data(changeset_id, config: ReplayToolConfig) -> str:
    osm_base_url = config.osm_base_url
    if not osm_base_url:
        raise Exception('osm_base_url not configured')
    meta_url = f'{osm_base_url}/api/0.6/changeset/{changeset_id}/download'
    response = requests.get(meta_url)
    status_code = response.status_code
    if status_code != 200:
        raise Exception(f'Status code {status_code} while getting changeset')
    return response.text
