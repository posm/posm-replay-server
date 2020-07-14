import requests
import time
import os
import tempfile

import psycopg2
import osm2geojson

from django.db import transaction, models
from typing import NewType, Tuple

from posm_replay.celery import app

from .models import (
    ReplayTool, LocalChangeSet,
    OSMElement, ReplayToolConfig,
)

from .utils.decorators import set_error_status_on_exception
from .utils.osm_api import (
    get_changeset_data,
    get_changeset_meta,
)
from .utils.osmium_handlers import (
    OSMElementsTracker,
    ElementsFilterHandler,
    AOIHandler,
    VersionHandler,
)
from .utils.common import (
    get_aoi_path,
    get_original_aoi_path,
    get_current_aoi_info,
    get_current_aoi_path,
    get_overpass_query,
    filter_elements_from_aoi_handler,

    # Typings
    FilteredElements,
)
from .utils.conflicts import (
    get_conflicting_elements,
    do_elements_conflict,

    # Typings
    ConflictingElements,
)

import logging
logger = logging.getLogger(__name__)


OVERPASS_API_URL = 'http://overpass-api.de/api/interpreter'
OSM_API_MAX_ELEMENTS_LIMIT = 10000

OSMOSIS_COMMAND_TIMEOUT_SECS = 10

ElementTypeStr = NewType('ElementTypeStr', str)
AOIHandlerTriplet = NewType('AOIHandlerTriplet', Tuple[AOIHandler, AOIHandler, AOIHandler])


def get_first_changeset_id() -> int:
    config = ReplayToolConfig.load()
    db_config = {
        'host': config.posm_db_host,
        'dbname': config.posm_db_name,
        'user': config.posm_db_user,
        'password': config.posm_db_password,
    }
    with psycopg2.connect(**db_config) as conn:
        with conn.cursor() as cur:
            changeset_query = 'select id from changesets where num_changes > 0 order by id asc limit 1;'
            cur.execute(changeset_query)
            row = cur.fetchone()
            return row[0]


def collect_changesets_from_apidb(first_changeset_id):
    config = ReplayToolConfig.load()
    changeset_id = first_changeset_id
    while True:
        meta_data = get_changeset_meta(changeset_id, config)
        if meta_data is None:
            break
        time.sleep(0.1)
        # Increment changeset id to get next one
        data = get_changeset_data(changeset_id, config)

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
    prev_state=ReplayTool.STATUS_NOT_TRIGGERRED,
    curr_state=ReplayTool.STATUS_GATHERING_CHANGESETS
)
def gather_changesets():
    try:
        first_changeset_id = get_first_changeset_id()
    except Exception as e:
        logger.warning('Error getting first changeset id', exc_info=True)
        raise e

    # Now collect changesets
    try:
        collect_changesets_from_apidb(first_changeset_id)
    except Exception as e:
        logger.warning('Error collecting changesets from apidb', exc_info=True)
        raise e


def get_original_element_versions():
    original_aoi_path = get_original_aoi_path()
    version_handler = VersionHandler()
    version_handler.apply_file(original_aoi_path)
    return version_handler


@set_error_status_on_exception(
    prev_state=ReplayTool.STATUS_EXTRACTING_UPSTREAM_AOI,
    curr_state=ReplayTool.STATUS_EXTRACTING_LOCAL_AOI
)
def get_local_aoi_extract():
    config = ReplayToolConfig.load()
    db_user = config.posm_db_user
    db_password = config.posm_db_password
    osmosis_aoi_root = config.osmosis_aoi_root
    osmosis_db_host = config.osmosis_db_host
    aoi_name = config.aoi_name

    if not db_user or not db_password or not osmosis_db_host or not osmosis_aoi_root or not aoi_name:
        raise Exception(
            'osmosis_aoi_root, aoi_name, osmosis_db_host, posm_db_user and posm_db_password must all be configured')

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
    prev_state=ReplayTool.STATUS_GATHERING_CHANGESETS,
    curr_state=ReplayTool.STATUS_EXTRACTING_UPSTREAM_AOI
)
def get_current_aoi_extract():
    [w, s, e, n] = get_current_aoi_info()['bbox']
    overpass_query = get_overpass_query(s, w, n, e)
    overpass_api_url = ReplayToolConfig.load().overpass_api_url
    response = requests.get(overpass_api_url, data={'data': overpass_query})

    # Write response to <aoi_path>/current_aoi.osm
    with open(get_current_aoi_path(), 'wb') as f:
        f.write(response.content)
    return True


def track_elements_from_local_changesets() -> OSMElementsTracker:
    tracker = OSMElementsTracker()
    for changeset in LocalChangeSet.objects.all():
        # Create named temp file
        tf = tempfile.NamedTemporaryFile(suffix='.osc')
        tf.write(changeset.changeset_data.encode('utf-8'))
        tf.seek(0)
        filter_handler = ElementsFilterHandler(tracker)
        filter_handler.apply_file(tf.name)

    # Now we have refed/added/modified/deleted nodes in tracker
    return tracker


def track_elements_and_get_aoi_handlers(tracker: OSMElementsTracker) -> Tuple[AOIHandler, AOIHandler, AOIHandler]:
    aoi_path = get_aoi_path()
    local_aoi_path = os.path.join(aoi_path, 'local_aoi.osm')
    current_aoi_path = os.path.join(aoi_path, 'current_aoi.osm')
    original_aoi_path = get_original_aoi_path()

    original_aoi_handler = AOIHandler(tracker, '/tmp/original_referenced.osm')
    original_aoi_handler.apply_file_and_cleanup(original_aoi_path)

    local_aoi_handler = AOIHandler(tracker, '/tmp/local_referenced.osm')
    local_aoi_handler.apply_file_and_cleanup(local_aoi_path)

    upstream_aoi_handler = AOIHandler(tracker, '/tmp/upstream_referenced.osm')
    upstream_aoi_handler.apply_file_and_cleanup(current_aoi_path)

    return original_aoi_handler, local_aoi_handler, upstream_aoi_handler


def save_elements_count_data(local_aoi_handler: AOIHandler, upstream_aoi_handler: AOIHandler):
    # Add total count data to replay_tool
    tool = ReplayTool.objects.get()
    tool.elements_data = {
        'local': {
            'nodes_count': local_aoi_handler.nodes_count,
            'ways_count': local_aoi_handler.ways_count,
            'relations_count': local_aoi_handler.relations_count,
        },
        'upstream': {
            'nodes_count': upstream_aoi_handler.nodes_count,
            'ways_count': upstream_aoi_handler.ways_count,
            'relations_count': upstream_aoi_handler.relations_count,
        }
    }
    tool.save()


def add_added_deleted_and_modified_elements(tracker: OSMElementsTracker,
                                            local_aoi_handler: OSMElementsTracker,
                                            upstream_aoi_handler: OSMElementsTracker):
    local_added_elements = tracker.get_added_elements(local_aoi_handler)
    local_modified_elements = tracker.get_modified_elements(local_aoi_handler)
    local_deleted_elements = tracker.get_deleted_elements(local_aoi_handler)

    upstream_referenced_elements = tracker.get_referenced_elements(upstream_aoi_handler)

    upstream_deleted_elements = tracker.get_deleted_elements(upstream_aoi_handler)
    # HANDLE DELETED ELEMENTS
    # Check if existing partially-resolved/resolved elememts are deleted in upstream aoi
    for elemtype, elems in upstream_deleted_elements.items():
        elem_ids = [x['id'] for x in elems]
        existing_resolved_elements = OSMElement.objects.filter(
            type=elemtype[:-1],
            element_id__in=elem_ids,
            status=OSMElement.STATUS_RESOLVED,
        )
        existing_unresolved_elements = OSMElement.objects.filter(
            ~models.Q(status=OSMElement.STATUS_RESOLVED),
            type=elemtype[:-1],
            element_id__in=elem_ids,
        )
        # Set status to partially_resolved for resolved element and for other just update upstream data
        existing_resolved_elements.update(
            upstream_data={'deleted': True},
            status=OSMElement.STATUS_PARTIALLY_RESOLVED
        )
        existing_unresolved_elements.update(
            upstream_data={'deleted': True},
            status=OSMElement.STATUS_PARTIALLY_RESOLVED
        )

    upstream_referenced_elements_map = {
        elemtype: {
            x['id']: x
            for x in elems
        } for elemtype, elems in upstream_referenced_elements.items()
    }

    for elemtype, elems in local_modified_elements.items():
        for elem in elems:
            upstream_data = upstream_referenced_elements_map[elemtype][elem['id']]
            if not upstream_data.get('tags'):
                upstream_data.pop('tags', None)
            # if same, mark resolved, else mark unresolved
            # Get Object, which potentially already exists
            osmelem = OSMElement.objects.filter(
                type=elemtype[:-1],  # the elemtype is plural: nodes, ways, etc but type is singular
                element_id=elem['id'],
            ).first()

            # if not exists, just create
            if osmelem is None:
                OSMElement.objects.create(
                    type=elemtype[:-1],  # the elemtype is plural: nodes, ways, etc but type is singular
                    element_id=elem['id'],
                    local_data=elem,
                    upstream_data=upstream_data,
                    local_state=OSMElement.LOCAL_STATE_MODIFIED,
                    status=OSMElement.STATUS_RESOLVED,
                )
            else:
                # Element already exists, check for attributes conflicts in element upstream
                # and currently pulled upstream_data
                # Do nothing if already pushed
                if elem.status != OSMElement.STATUS_PUSHED:
                    conflicting = do_elements_conflict(elem.upstream_data, upstream_data)
                    if conflicting and elem.status == OSMElement.STATUS_RESOLVED:
                        elem.status = OSMElement.STATUS_PARTIALLY_RESOLVED
                    elem.save()

    for elemtype, elems in local_added_elements.items():
        for elem in elems:
            # TODO: get and check if it is already pushed
            OSMElement.objects.update_or_create(
                type=elemtype[:-1],  # the elemtype is plural: nodes, ways, etc but type is singular
                element_id=elem['id'],
                defaults=dict(
                    local_data=elem,
                    local_state=OSMElement.LOCAL_STATE_ADDED,
                    status=OSMElement.STATUS_RESOLVED,
                )
            )

    for elemtype, elems in local_deleted_elements.items():
        for elem in elems:
            upstream_data = upstream_referenced_elements_map[elemtype].get(elem['id']) or {}
            # TODO: get and check if it is already pushed
            OSMElement.objects.update_or_create(
                type=elemtype[:-1],  # the elemtype is plural: nodes, ways, etc but type is singular
                element_id=elem['id'],
                defaults=dict(
                    local_data=elem,
                    upstream_data=upstream_data,
                    local_state=OSMElement.LOCAL_STATE_DELETED,
                    status=OSMElement.STATUS_RESOLVED,
                )
            )


def get_referenced_and_deleted_elements(elements: FilteredElements) -> dict:
    return {
        'nodes': {**elements['referenced']['nodes'], **elements['deleted']['nodes']},
        'ways': {**elements['referenced']['ways'], **elements['deleted']['ways']},
        'relations': {**elements['referenced']['relations'], **elements['deleted']['relations']},
    }


@set_error_status_on_exception(
    prev_state=ReplayTool.STATUS_EXTRACTING_LOCAL_AOI,
    curr_state=ReplayTool.STATUS_DETECTING_CONFLICTS
)
def filter_referenced_elements_and_detect_conflicts():
    tracker = track_elements_from_local_changesets()
    handlers: AOIHandlerTriplet = track_elements_and_get_aoi_handlers(tracker)
    original_aoi_handler, local_aoi_handler, upstream_aoi_handler = handlers

    # Get versions
    version_handler: VersionHandler = get_original_element_versions()

    save_elements_count_data(local_aoi_handler, upstream_aoi_handler)

    upstream_elements: FilteredElements = filter_elements_from_aoi_handler(tracker, upstream_aoi_handler)
    local_elements: FilteredElements = filter_elements_from_aoi_handler(tracker, local_aoi_handler)

    # Find and create OSMElement objects for each of the added/modified/deleted elements
    add_added_deleted_and_modified_elements(tracker, local_aoi_handler, upstream_aoi_handler)

    # Get conflicting elements ids from the tracker and aoi handlers
    conflicting_elements: ConflictingElements = get_conflicting_elements(
        get_referenced_and_deleted_elements(local_elements),
        get_referenced_and_deleted_elements(upstream_elements),
        version_handler,
    )

    for elemtype, ids in conflicting_elements.items():
        OSMElement.objects.filter(
            ~models.Q(local_state=OSMElement.LOCAL_STATE_CONFLICTING),  # Only pull the ones that are not conflicting
            # The conflicting elements are the ones from previous resolving and are already taken care of in 
            # add_added_deleted_and_modified_elements() method
            type=elemtype[:-1],
            element_id__in=ids,
        ).update(
            status=OSMElement.STATUS_UNRESOLVED,
            local_state=OSMElement.LOCAL_STATE_CONFLICTING
        )

    # NOW add referring ways and relations
    for rid, relation in local_aoi_handler.referring_relations.items():
        # TODO: check if already pushed
        OSMElement.objects.get_or_create(
            element_id=rid,
            type=OSMElement.TYPE_RELATION,
            defaults=dict(
                local_data=relation,
                upstream_data=relation,
                local_state=OSMElement.LOCAL_STATE_REFERRING,
                status=OSMElement.STATUS_UNRESOLVED,
            )
        )

    for wid, way in local_aoi_handler.referring_ways.items():
        # TODO: check if already pushed
        OSMElement.objects.get_or_create(
            element_id=wid,
            type=OSMElement.TYPE_WAY,
            defaults=dict(
                local_data=way,
                upstream_data=way,
                local_state=OSMElement.LOCAL_STATE_REFERRING,
                status=OSMElement.STATUS_UNRESOLVED,
            )
        )

    # Get conflicting nodes and create map
    nodes_map = {
        node.element_id: node
        for node in OSMElement.objects.filter(
            type=OSMElement.TYPE_NODE,
            local_state=OSMElement.LOCAL_STATE_CONFLICTING,
        )
    }

    # Add link between nodes and referring elements(ways and relations)
    for nid, referring_wayids in local_aoi_handler.nodes_references_by_ways.items():
        node = nodes_map.get(nid)
        if not node:
            continue
        # NOTE: Just use the first refering way
        # This is because, the conflict is in fact in the position of node contained by
        # one of the ways, and it is enough that any of the ways be shown,
        # at least for now.
        referring_wayid = referring_wayids[0]  # There should be at least one entry
        referrer = OSMElement.objects.get(element_id=referring_wayid, type=OSMElement.TYPE_WAY)
        node.reffered_by = referrer
        node.save()

    # Do the same for nodes and relations
    for nid, referring_relationids in local_aoi_handler.nodes_references_by_relations.items():
        node = nodes_map.get(nid)
        # If the node already has some refferer(probably way) just ignore this one
        if not node or node.reffered_by:
            continue
        # NOTE: Just use the first refering relation
        # This is because, the conflict is in fact in the position of node contained by
        # one of the relations, and it is enough that any of the relations be shown,
        # at least for now.
        referring_relation_id = referring_relationids[0]  # There should be at least one entry
        referrer = OSMElement.objects.get(element_id=referring_relation_id, type=OSMElement.TYPE_RELATION)
        node.reffered_by = referrer
        node.save()
    return original_aoi_handler, local_aoi_handler, upstream_aoi_handler


@set_error_status_on_exception(
    prev_state=ReplayTool.STATUS_DETECTING_CONFLICTS,
    curr_state=ReplayTool.STATUS_CREATING_GEOJSONS,
)
def generate_all_geojsons(original_ref_path, local_ref_path, upstream_ref_path):
    original_geojson = generate_geojsons(original_ref_path)
    local_geojson = generate_geojsons(local_ref_path)
    upstream_geojson = generate_geojsons(upstream_ref_path)

    # Keep track of nodes geojson only, because some nodes are not populated in geojson
    # whenever the node is referenced by a way or relation
    original_nodes_geojson = {
        feature['properties']['id']: feature for feature in
        generate_geojsons(original_ref_path + '.nodes.osm')['features']
    }
    upstream_nodes_geojson = {
        feature['properties']['id']: feature for feature in
        generate_geojsons(upstream_ref_path + '.nodes.osm')['features']
    }
    local_nodes_geojson = {
        feature['properties']['id']: feature for feature in
        generate_geojsons(local_ref_path + '.nodes.osm')['features']
    }

    @transaction.atomic
    def _set_geojson(geojson, obj_attr):
        for feature in geojson['features']:
            type = feature['properties']['type']
            id = feature['properties']['id']
            obj, _ = OSMElement.objects.get_or_create(
                element_id=id, type=type,
                defaults={
                    'local_data': feature['properties'],
                    'upstream_data': feature['properties'],
                }
            )
            obj.__setattr__(obj_attr, feature)
            obj.save()

    _set_geojson(original_geojson, 'original_geojson')
    _set_geojson(local_geojson, 'local_geojson')
    _set_geojson(upstream_geojson, 'upstream_geojson')

    # Set geojsons of nodes which do not have geojsons
    with transaction.atomic():
        for obj in OSMElement.objects.filter(type=OSMElement.TYPE_NODE):
            obj.original_geojson = obj.original_geojson or original_nodes_geojson.get(obj.element_id, {})
            obj.upstream_geojson = obj.upstream_geojson or upstream_nodes_geojson.get(obj.element_id, {})
            obj.local_geojson = obj.local_geojson or local_nodes_geojson.get(obj.element_id, {})
            obj.save()

    return True


def generate_geojsons(osmpath):
    with open(osmpath, 'r', encoding='utf-8') as f:
        xml = f.read()
    geojson = osm2geojson.xml2geojson(xml)
    return geojson


# @set_error_status_on_exception(
#     prev_state=ReplayTool.STATUS_RESOLVING_CONFLICTS,
#     curr_state=ReplayTool.STATUS_PUSH_CONFLICTS
# )
def create_and_push_changeset(osm_oauth_backend, to_push_elements_ids=None):
    # TODO: handle to_push_elements_ids
    all_elems = OSMElement.objects.filter(
        ~models.Q(local_state=OSMElement.LOCAL_STATE_REFERRING),
        ~models.Q(status=OSMElement.STATUS_UNRESOLVED),
        ~models.Q(status=OSMElement.STATUS_PUSHED),
    )
    if all_elems.count() < OSM_API_MAX_ELEMENTS_LIMIT:
        # Create changeset
        changeset = osm_oauth_backend.get_or_create_changeset()
        # Upload the changeset
        osm_oauth_backend.upload_changeset(changeset.changeset_id)
        # Close the changeset
        osm_oauth_backend.close_changeset(changeset.changeset_id)

        # TODO: update status of osm elements to pushed
        # and probably do clean up
        return

    # Else, send elements in chunk
    logger.warn(f"There are more elements than the limit {OSM_API_MAX_ELEMENTS_LIMIT}. Pushing in chunks.")
    while True:
        to_push_elements_ids: set = {}
        # Get Relations and the referred elements in chunk
        relations = OSMElement.objects.filter(
            ~models.Q(local_state=OSMElement.LOCAL_STATE_REFERRING),
            ~models.Q(status=OSMElement.STATUS_UNRESOLVED),
            ~models.Q(status=OSMElement.STATUS_PUSHED),
            type=OSMElement.TYPE_RELATION,
        ).prefetch_related('referenced_elements')[:OSM_API_MAX_ELEMENTS_LIMIT]

        for relation in relations:
            curr_count = len(to_push_elements_ids)
            ref_elements = relation.get_nested_referenced_elements()
            if curr_count + 1 + len(ref_elements) >= OSM_API_MAX_ELEMENTS_LIMIT:
                # TODO: do push and call this function recursively
                break
            to_push_elements_ids.add(relation.id)
            to_push_elements_ids = to_push_elements_ids.union({x.id for x in ref_elements})

        # Get Ways and the referred elements in chunk
        ways = OSMElement.objects.filter(
            ~models.Q(local_state=OSMElement.LOCAL_STATE_REFERRING),
            ~models.Q(status=OSMElement.STATUS_UNRESOLVED),
            ~models.Q(status=OSMElement.STATUS_PUSHED),
            type=OSMElement.TYPE_WAY,
        ).prefetch_related('referenced_elements')[:OSM_API_MAX_ELEMENTS_LIMIT - len(to_push_elements_ids)]
        for way in ways:
            curr_count = len(to_push_elements_ids)
            ref_elements = way.get_nested_referenced_elements()
            if curr_count + 1 + len(ref_elements) >= OSM_API_MAX_ELEMENTS_LIMIT:
                # TODO: do push and call this function recursively
                break
            to_push_elements_ids.add(way.id)
            to_push_elements_ids = to_push_elements_ids.union({x.id for x in ref_elements})

        # Get nodes
        nodes = OSMElement.objects.filter(
            ~models.Q(local_state=OSMElement.LOCAL_STATE_REFERRING),
            ~models.Q(status=OSMElement.STATUS_UNRESOLVED),
            ~models.Q(status=OSMElement.STATUS_PUSHED),
            type=OSMElement.TYPE_NODE,
        )[:OSM_API_MAX_ELEMENTS_LIMIT - len(to_push_elements_ids)]
        to_push_elements_ids = to_push_elements_ids.union({x.id for x in nodes})

        create_and_push_changeset(osm_oauth_backend, to_push_elements_ids)


@app.task
def task_prepare_data_for_replay_tool(start_state: str = None):
    """
    @start_state: Begin from a particular state
    This is the function that does all the behind the scene tasks like:
    - gathering changesets from local apidb
    - gathering current aoi extract
    - filtering out referenced nodes
    - marking added, modified, deleted nodes
    """
    RT = ReplayTool
    state_order = RT.STATE_ORDER

    if start_state is None or state_order[start_state] <= state_order[RT.STATUS_NOT_TRIGGERRED]:
        logger.info("Gathering local changesets")
        gather_changesets()
        logger.info("Gathered local changesets")

    if start_state is None or state_order[start_state] <= state_order[RT.STATUS_GATHERING_CHANGESETS]:
        logger.info("Get current aoi extract")
        get_current_aoi_extract()
        logger.info("Got current aoi extract")

    if start_state is None or state_order[start_state] <= state_order[RT.STATUS_EXTRACTING_UPSTREAM_AOI]:
        logger.info("Get local aoi extract")
        get_local_aoi_extract()
        logger.info("Got local aoi extract")

    if start_state is None or state_order[start_state] <= state_order[RT.STATUS_EXTRACTING_LOCAL_AOI]:
        logger.info("Filtering referenced elements")
        original_handler, local_handler, upstream_handler = \
            filter_referenced_elements_and_detect_conflicts()
        logger.info("Filtered referenced elements")

    if start_state is None or state_order[start_state] <= state_order[RT.STATUS_DETECTING_CONFLICTS]:
        logger.info("Generating geojsons")
        generate_all_geojsons(
            original_handler.ref_osm_path,
            local_handler.ref_osm_path,
            upstream_handler.ref_osm_path
        )
    if start_state is None or state_order[start_state] <= state_order[RT.STATUS_CREATING_GEOJSONS]:
        logger.info("Generated geojsons")
        replay_tool = RT.objects.get()
        replay_tool.state = replay_tool.STATUS_RESOLVING_CONFLICTS
        if OSMElement.get_conflicting_elements().count() > 0:
            logger.info("Conflicts detected")
            replay_tool.is_current_state_complete = False
        else:
            logger.info("No conflicts detected")
            replay_tool.is_current_state_complete = True
    replay_tool.save()
