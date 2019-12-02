import os

from replay_tool.serializers import NodeSerializer


def get_aoi_path() -> str:
    aoi_root = os.environ.get('AOI_ROOT')
    aoi_name = os.environ.get('AOI_NAME')
    if not aoi_root or not aoi_name:
        raise Exception('AOI_ROOT and AOI_NAME must both be defined in env')
    return os.path.join(aoi_root, aoi_name)


def get_local_aoi_path() -> str:
    return os.path.join(get_aoi_path(), 'local_aoi.osm')


def get_current_aoi_path() -> str:
    return os.path.join(get_aoi_path(), 'current_aoi.osm')


def get_overpass_query(s, w, n, e) -> str:
    return f'(node({s},{w},{n},{e});<;>>;>;);out meta;'


def filter_nodes_from_tracker(tracker):
    """This function is used inside reducer to filter nodes"""
    def filter_func(acc: dict, id_node: (int, object)):
        # id_node is from local/upstream aoi
        nid, node = id_node
        if nid in tracker.added_elements['nodes']:
            acc['added'][nid] = node
        elif nid in tracker.modified_elements['nodes']:
            acc['modified'][nid] = node
        elif nid in tracker.deleted_elements['nodes']:
            acc['deleted'][nid] = node
        if nid in tracker.referenced_elements['nodes']:
            acc['referenced'][nid] = node
        return acc
    return filter_func


def do_nodes_conflict(node1_serialized: dict, node2_serialized: dict) -> bool:
    """The nodes node1 and node2 represent the same node(same id) and are from
    local and upstream db respectively
    """
    if node1_serialized['visible'] != node2_serialized['visible']:
        return True

    # pop irrelevant keys and attributes
    node1_serialized.pop('timestamp')
    node1_serialized.pop('uid')
    node1_serialized.pop('user')
    node1_serialized.pop('changeset')
    node1_serialized.pop('location')

    node2_serialized.pop('timestamp')
    node2_serialized.pop('uid')
    node2_serialized.pop('user')
    node2_serialized.pop('changeset')
    node2_serialized.pop('location')

    n1_tags = node1_serialized.pop('tags', [])
    n2_tags = node2_serialized.pop('tags', [])

    if node1_serialized != node2_serialized:
        return True

    if len(n1_tags) != len(n2_tags):
        return True
    n1_tags_keyvals = {x['k']: x['v'] for x in n1_tags}
    n2_tags_keyvals = {x['k']: x['v'] for x in n2_tags}

    return n1_tags_keyvals != n2_tags_keyvals


def get_conflicting_nodes(local_referenced_nodes, aoi_referenced_nodes):
    """
    Returns [(serialized_local_node1, seriaalized_aoi_node1), ...] of conflicting nodes
    """
    conflicting_nodes = []
    for l_nid, local_node in local_referenced_nodes.items():
        # NOTE: Assumption that l_nid is always present in aoi_referenced_nodes
        # which is a very valid assumption
        aoi_node = aoi_referenced_nodes[l_nid]
        serialized_aoi_node = NodeSerializer(aoi_node).data
        serialized_local_node = NodeSerializer(local_node).data
        if do_nodes_conflict(serialized_local_node, serialized_aoi_node):
            conflicting_nodes.append((serialized_local_node, serialized_aoi_node))
    return conflicting_nodes
