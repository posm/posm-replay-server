import requests
import time
import os

import psycopg2

from .models import ReplayTool, LocalChangeSet

import logging
logger = logging.getLogger(__name__)


def get_first_changeset_id():
    config = {
        'host': os.environ.get('POSM_HOSTNAME', 'posm.io'),
        'dbname': 'osm',
        'user': 'osm',
        'password': 'awesomeposm',
    }
    with psycopg2.connect(**config) as conn:
        with conn.cursor() as cur:
            changeset_query = 'select id from changesets where num_changes > 0 order by id asc limit 1;'
            cur.execute(changeset_query)
            row = cur.fetchone()
            return row[0]


def _get_changeset_meta(changeset_id):
    osm_base_url = os.environ.get('OSM_BASE_URL', 'http://localhost:3000')
    meta_url = f'{osm_base_url}/api/0.6/changeset/{changeset_id}'
    response = requests.get(meta_url)
    status_code = response.status_code
    if status_code == 404:
        return None
    if status_code != 200:
        raise Exception(f'Status code {status_code} while getting changeset')
    return response.text


def _get_changeset_data(changeset_id):
    osm_base_url = os.environ.get('OSM_BASE_URL', 'http://localhost:3000')
    meta_url = f'{osm_base_url}/api/0.6/changeset/{changeset_id}/download'
    response = requests.get(meta_url)
    status_code = response.status_code
    if status_code != 200:
        raise Exception(f'Status code {status_code} while getting changeset')
    return response.text


def collect_changesets_from_apidb(first_changeset_id):
    changeset_id = first_changeset_id
    while True:
        meta_data = _get_changeset_meta(changeset_id)
        if meta_data is None:
            break
        time.sleep(0.1)
        # Increment changeset id to get next one
        data = _get_changeset_data(changeset_id)

        # Save changeset to db
        LocalChangeSet.objects.create(
            changeset_id=changeset_id,
            changeset_meta=meta_data,
            changeset_data=data
        )
        time.sleep(0.1)

        changeset_id += 1

    return True


def gather_changesets(self):
    replay_tool_status, _ = ReplayTool.objects.get_or_create()
    if replay_tool_status.errorred is True:
        raise Exception(f'Relay tool has errorred while {replay_tool_status.status}')

    if replay_tool_status.status != ReplayTool.STATUS_NOT_TRIGGERRED:
        raise Exception('Relay tool has already been triggered. No point in gathering changesets.')

    replay_tool_status.status = ReplayTool.STATUS_GATHERING_CHANGESETS
    replay_tool_status.current_state_completed = False
    replay_tool_status.save()

    try:
        first_changeset_id = get_first_changeset_id()
    except Exception:
        logger.warn('Error getting first changeset id', exc_info=True)
        replay_tool_status.errorred = True
        replay_tool_status.save()

    # Now collect changesets
    try:
        collect_changesets_from_apidb(first_changeset_id)
        replay_tool_status.current_state_completed = True
        replay_tool_status.save()
    except Exception:
        logger.warn('Error collecting changesets from apidb', exc_info=True)
        replay_tool_status.errorred = True
        replay_tool_status.save()
