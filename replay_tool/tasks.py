import requests
import time
import os
import json

import psycopg2

from .models import ReplayTool, LocalChangeSet

import logging
logger = logging.getLogger(__name__)


OVERPASS_API_URL = 'http://overpass-api.de/api/interpreter'


def get_overpass_query(s, w, n, e):
    return f'(node({s},{w},{n},{e});<;>>;>;);out meta;'


def get_first_changeset_id() -> str:
    config = {
        'host': os.environ.get('POSM_HOSTNAME'),
        'dbname': os.environ.get('POSM_DB_NAME'),
        'user': os.environ.get('POSM_DB_USER'),
        'password': os.environ.get('POSM_DB_PASSWORD'),
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
    osm_base_url = os.environ.get('OSM_BASE_URL')
    if not osm_base_url:
        raise Exception('OSM_BASE_URL env not set')
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


def gather_changesets():
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


def get_local_aoi_extract():
    pass


def get_current_aoi_extract():
    replay_tool, _ = ReplayTool.objects.get()
    if replay_tool.errorred is True:
        raise Exception(f'Relay tool has errorred while {replay_tool.status}')

    if replay_tool.status != ReplayTool.STATUS_GATHERING_CHANGESETS or not replay_tool.current_state_completed:
        raise Exception('Current AOI extract can be run only after gathering changesets is completed')

    replay_tool.status = ReplayTool.STATUS_EXTRACTING_UPSTREAM_AOI
    replay_tool.current_state_completed = False
    replay_tool.save()

    aoi_root = os.environ.get('AOI_ROOT')
    aoi_name = os.environ.get('AOI_NAME')
    if not aoi_root or not aoi_name:
        raise Exception('AOI_ROOT and AOI_NAME must both be defined in env')
    manifest_path = os.path.join(aoi_root, aoi_name, 'manifest.json')

    # TODO: Check if manifest file exist
    with open(manifest_path) as f:
        manifest = json.load(f)
        [w, s, e, n] = manifest['bbox']

    overpass_query = get_overpass_query(s, w, n, e)
    response = requests.get(OVERPASS_API_URL, data={'data': overpass_query})

    # Write response to <aoi_root>/current_aoi.osm
    with open(os.path.join(aoi_root, 'current_aoi.osm'), 'wb') as f:
        f.write(response.content)

    replay_tool.current_state_completed = False
    replay_tool.save()
    return True


def task_prepare_data_for_replay_tool():
    """
    This is the function that does all the behind the scene tasks like:
    - gathering changesets from local apidb
    - gathering current aoi extract
    - filtering out referenced nodes
    - marking added, modified, deleted nodes
    """
    logger.info("Gathering local changesets")
    gather_changesets()
    logger.info("Gathered local changesets")

    logger.info("Get current aoi extract")
    get_current_aoi_extract()
    logger.info("Got current aoi extract")

    logger.info("Get local aoi extract")
    get_local_aoi_extract()
    logger.info("Got local aoi extract")
