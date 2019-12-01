import requests
import time
import os
import json

import tempfile

import psycopg2

from .models import ReplayTool, LocalChangeSet
from .utils.decorators import set_error_status_on_exception
from .utils.osm_api import get_changeset_data, get_changeset_meta
from .utils.osmium_handlers import OSMElementsTracker, ElementsFilterHandler

import logging
logger = logging.getLogger(__name__)


OVERPASS_API_URL = 'http://overpass-api.de/api/interpreter'

OSMOSIS_COMMAND_TIMEOUT_SECS = 10


def get_aoi_path():
    aoi_root = os.environ.get('AOI_ROOT')
    aoi_name = os.environ.get('AOI_NAME')
    if not aoi_root or not aoi_name:
        raise Exception('AOI_ROOT and AOI_NAME must both be defined in env')
    return os.path.join(aoi_root, aoi_name)


def get_overpass_query(s, w, n, e):
    return f'(node({s},{w},{n},{e});<;>>;>;);out meta;'


def get_first_changeset_id() -> int:
    config = {
        'host': os.environ.get('POSM_DB_HOST'),
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


def collect_changesets_from_apidb(first_changeset_id):
    changeset_id = first_changeset_id
    while True:
        meta_data = get_changeset_meta(changeset_id)
        if meta_data is None:
            break
        time.sleep(0.1)
        # Increment changeset id to get next one
        data = get_changeset_data(changeset_id)

        # Save changeset to db
        LocalChangeSet.objects.create(
            changeset_id=changeset_id,
            changeset_meta=meta_data,
            changeset_data=data
        )
        time.sleep(0.1)

        changeset_id += 1

    return True


@set_error_status_on_exception(
    prev_status=ReplayTool.STATUS_NOT_TRIGGERRED,
    curr_status=ReplayTool.STATUS_GATHERING_CHANGESETS
)
def gather_changesets():
    try:
        first_changeset_id = get_first_changeset_id()
    except Exception as e:
        logger.warn('Error getting first changeset id', exc_info=True)
        raise e

    # Now collect changesets
    try:
        collect_changesets_from_apidb(first_changeset_id)
    except Exception as e:
        logger.warn('Error collecting changesets from apidb', exc_info=True)
        raise e


@set_error_status_on_exception(
    prev_status=ReplayTool.STATUS_EXTRACTING_UPSTREAM_AOI,
    curr_status=ReplayTool.STATUS_EXTRACTING_LOCAL_AOI
)
def get_local_aoi_extract():
    db_user = os.environ.get('POSM_DB_USER')
    db_password = os.environ.get('POSM_DB_PASSWORD')
    osmosis_aoi_root = os.environ.get('OSMOSIS_AOI_ROOT')
    osmosis_db_host = os.environ.get('OSMOSIS_DB_HOST')
    aoi_name = os.environ.get('AOI_NAME')

    if not db_user or not db_password or not osmosis_db_host or not osmosis_aoi_root or not aoi_name:
        raise Exception('OSMOSIS_AOI_ROOT, AOI_NAME, OSMOSIS_DB_HOST, POSM_DB_USER and POSM_DB_PASSWORD must all be defined in env')

    path = os.path.join(osmosis_aoi_root, aoi_name, 'local_aoi.osm')
    command = f'''osmosis --read-apidb host={osmosis_db_host} user={db_user} \
        password={db_password} validateSchemaVersion=no --write-xml file={path}
    '''
    # Write command to named pipe
    with open('osmosis_command_reader.fifo', 'w') as f:
        f.write(command)

    # wait
    time.sleep(OSMOSIS_COMMAND_TIMEOUT_SECS)

    # Read result
    with open('osmosis_result_reader.fifo') as f:
        # Read the last line
        lines = [x for x in f.readlines() if x]
        if not lines:
            raise ('Time out while waiting for osmosis result')
        line = lines[-1]
        [err_code, *msg] = line.strip().split()
        if err_code == '0':
            return True
        else:
            raise Exception(' '.join(msg))


@set_error_status_on_exception(
    prev_status=ReplayTool.STATUS_GATHERING_CHANGESETS,
    curr_status=ReplayTool.STATUS_EXTRACTING_UPSTREAM_AOI
)
def get_current_aoi_extract():
    aoi_path = get_aoi_path()
    manifest_path = os.path.join(aoi_path, 'manifest.json')

    # TODO: Check if manifest file exist
    with open(manifest_path) as f:
        manifest = json.load(f)
        [w, s, e, n] = manifest['bbox']

    overpass_query = get_overpass_query(s, w, n, e)
    response = requests.get(OVERPASS_API_URL, data={'data': overpass_query})

    # Write response to <aoi_path>/current_aoi.osm
    with open(os.path.join(aoi_path, 'current_aoi.osm'), 'wb') as f:
        f.write(response.content)
    return True


def track_elements_from_local_changesets():
    tracker = OSMElementsTracker()
    for changeset in LocalChangeSet.objects.all():
        # Create named temp file
        tf = tempfile.NamedTemporaryFile(suffix='.osm')
        filter_handler = ElementsFilterHandler(tracker)
        filter_handler.apply_file(tf.name)
        # TODO: check if tracker is updated NOTE: hope that tracker is updated
    # Now we have refed/added/modified/deleted nodes

    # TODO: Get nodes info from Updated Local AOI and save to db

    # TODO: Get nodes info from updated Upstream AOI and save to db

    # TODO: Compare them and flag conflicting if they do not match


@set_error_status_on_exception(
    prev_status=ReplayTool.STATUS_EXTRACTING_LOCAL_AOI,
    curr_status=ReplayTool.STATUS_FILTERING_REFERENCED_OSM_ELEMENTS
)
def filter_referenced_columns():
    aoi_path = get_aoi_path()

    tracker = track_elements_from_local_changesets()


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

    logger.info("Filtering referenced columns")
    filter_referenced_columns()
    logger.info("Filtered referenced columns")
