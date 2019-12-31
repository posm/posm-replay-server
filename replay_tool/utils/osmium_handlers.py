import osmium
import os

from typing import Dict, List

from replay_tool.serializers.osm import (
    NodeSerializer,
    WaySerializer,
    RelationSerializer,
)


class VersionHandler(osmium.SimpleHandler):
    """
    Stores versions of elements
    """
    def __init__(self):
        super().__init__()
        self.nodes_versions = dict()
        self.ways_versions = dict()
        self.relations_versions = dict()

    def node(self, n):
        self.nodes_versions[n.id] = n.version

    def way(self, w):
        self.ways_versions[w.id] = w.version

    def relation(self, r):
        self.relations_versions[r.id] = r.version


class AOIHandler(osmium.SimpleHandler):
    """
    Stores AOI elements as keys values pair, along with total count
    @tracker: An instance of OSMElementsTracker class
        This is used to filter elements referenced/added in the tracker
    @ref_osm_path: filepath(osm) string for re-storing referenced elements
    """
    def __init__(self, tracker, ref_osm_path):
        super().__init__()
        self.tracker = tracker
        self.ref_osm_path = ref_osm_path
        self.nodes_references_by_ways: Dict[int, List[int]]
        self.nodes_references_by_relations: Dict[int, List[int]]
        # TODO: may need ways references by relations and
        # relations references by relations

        # osmfile to write referenced/added elements only
        try:
            os.remove(ref_osm_path)
        except OSError:
            pass

        self.writer = osmium.SimpleWriter(ref_osm_path)

        self.nodes_count = 0
        self.ways_count = 0
        self.relations_count = 0

        self.nodes: Dict[int, dict] = {}
        self.ways: Dict[int, dict] = {}
        self.relations: Dict[int, dict] = {}
        self.referring_ways: Dict[int, dict] = {}
        self.referring_relations: Dict[int, dict] = {}

        self._nodes: Dict[int, object] = {}
        self._ways: Dict[int, object] = {}
        self._relations: Dict[int, object] = {}

    def apply_file_and_cleanup(self, filename):
        self.apply_file(filename)

        # Add to writer, the referenced nodes and elements because they need to be shown in the ui
        # The idea is to add the ways and relations which reference nodes that
        # are referenced in the changesets
        for nodeid in self.tracker.referenced_elements['nodes']:
            for wayid in self.nodes_references_by_ways.get(nodeid, []):
                if wayid not in self.tracker.referenced_elements['ways']:
                    self.referring_ways[wayid] = WaySerializer(self._ways[wayid]).data
                    self.writer.add_way(self._ways[wayid])
            for relid in self.nodes_references_by_relations.get(nodeid, []):
                if relid not in self.tracker.referenced_elements['relations']:
                    self.referring_relations[relid] = RelationSerializer(self._relations[relid]).data
                    self.writer.add_relation(self._relations[relid])

        self.writer.close()

        self._nodes.clear()
        self._ways.clear()

    def node(self, n):
        self._nodes[n.id] = n
        self.nodes_count += 1
        if n.id in self.tracker.referenced_elements['nodes'] or n.id in self.tracker.added_elements['nodes']:
            self.nodes[n.id] = NodeSerializer(n).data
            # Write to writer to get osm file which is later converted to geojson
            self.writer.add_node(n)

    def way(self, w):
        self._ways[w.id] = w
        self.ways_count += 1
        # Add way to node references
        for node in w.nodes:
            self.nodes_references_by_ways[node.ref] = [
                *self.nodes_references_by_ways.get(node.ref, []),
                w.id
            ]

        if w.id in self.tracker.referenced_elements['ways'] or w.id in self.tracker.added_elements['ways']:
            self.ways[w.id] = WaySerializer(w).data
            # Write to writer to get osm file which is later converted to geojson
            for node in w.nodes:
                self.writer.add_node(self._nodes[node.ref])
            self.writer.add_way(w)

    def relation(self, r):
        self._relations[r.id] = r
        self.relations_count += 1
        # Add relation to node references
        for member in r.members:
            if member.type == 'node':
                self.nodes_references_by_relations[member.ref] = [
                    *self.nodes_references_by_relations.get(member.ref, []),
                    r.id
                ]
        if r.id in self.tracker.referenced_elements['relations'] or r.id in self.tracker.added_elements['relations']:
            self.relations[r.id] = RelationSerializer(r).data
            # Write to writer to get osm file which is later converted to geojson
            for member in r.members:
                if member.type == 'way':
                    for node in self._ways[member.ref].nodes:
                        self.writer.add_node(self._nodes[node.ref])
                    self.writer.add_way(self._ways[member.ref])
                elif member.type == 'node':
                    self.writer.add_node(self._nodes[member.ref])
                # TODO: member.type == 'relation'
            self.writer.add_relation(r)


class OSMElementsTracker:
    """
    Keeps tracks of added, referenced, modified and deleted elements.
    """
    def __init__(self):
        self.referenced_elements = {
            'nodes': set(), 'relations': set(), 'ways': set()
        }
        self.modified_elements = {
            'nodes': set(), 'relations': set(), 'ways': set()
        }
        self.added_elements = {
            'nodes': set(), 'relations': set(), 'ways': set()
        }
        self.deleted_elements = {
            'nodes': set(), 'relations': set(), 'ways': set()
        }

    def get_added_elements(self, aoi_handler):
        return {
            'nodes': [
                aoi_handler.nodes[k] for k in self.added_elements['nodes']
            ],
            'ways': [
                aoi_handler.ways[k] for k in self.added_elements['ways']
            ],
            'relations': [
                aoi_handler.relations[k] for k in self.added_elements['relations']
            ],
        }

    def get_deleted_elements(self, aoi_handler):
        return {
            'nodes': [
                aoi_handler.nodes[k] for k in self.deleted_elements['nodes']
            ],
            'ways': [
                aoi_handler.ways[k] for k in self.deleted_elements['ways']
            ],
            'relations': [
                aoi_handler.relations[k] for k in self.deleted_elements['relations']
            ],
        }

    def get_modified_elements(self, aoi_handler):
        return {
            'nodes': [
                aoi_handler.nodes[k] for k in self.modified_elements['nodes']
            ],
            'ways': [
                aoi_handler.ways[k] for k in self.modified_elements['ways']
            ],
            'relations': [
                aoi_handler.relations[k] for k in self.modified_elements['relations']
            ],
        }


class ElementsFilterHandler(osmium.SimpleHandler):
    """
    This will be applied to a changeset file, possibly to multiple changesets.
    And final result will be total collection of added/deleted/modified elements

    Parameters
    ----------
    elements_tracker: OSMElementsTracker
        An instance of OSMElementsTracker to track and update the added/deleted/modified/referenced elements.
        NOTE: this will be mutated.
    """
    def __init__(self, elements_tracker):
        super().__init__()
        self.elements_tracker = elements_tracker
        self.nodes: Dict[int, object] = {}
        self.ways: Dict[int, object] = {}
        self.relations: Dict[int, object] = {}

    @property
    def added_elements(self):
        return self.elements_tracker.added_elements

    @property
    def referenced_elements(self):
        return self.elements_tracker.referenced_elements

    @property
    def modified_elements(self):
        return self.elements_tracker.modified_elements

    @property
    def deleted_elements(self):
        return self.elements_tracker.deleted_elements

    def handle_element(self, element_type: str, element):
        if element.version == 1:
            self.added_elements[element_type].add(element.id)
        elif not element.visible:
            # If not visible and exists in self.added_elements,
            # remove it from added elements. Else, add as deleted and referenced
            if element.id not in self.added_elements[element_type]:
                self.deleted_elements[element_type].add(element.id)
                self.referenced_elements[element_type].add(element.id)
            else:
                self.added_elements[element_type].remove(element.id)
        else:
            # Add to modified elements only if it is not in added elements,
            # Because we have to flag it as added element
            # Once locally added, it does not matter if it is modified
            if element.id not in self.added_elements[element_type]:
                self.modified_elements[element_type].add(element.id)
                self.referenced_elements[element_type].add(element.id)

    def node(self, n):
        self.handle_element('nodes', n)

    def way(self, w):
        self.handle_element('ways', w)

    def relation(self, r):
        self.handle_element('relations', r)
