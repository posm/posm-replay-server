from typing import Dict


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
