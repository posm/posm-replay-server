import osmium

from replay_tool.serializers import NodeSerializer, WaySerializer, RelationSerializer


class AOIHandler(osmium.SimpleHandler):
    """
    Stores AOI elements as keys values pair.
    """
    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.nodes: dict = {}
        self.ways: dict = {}
        self.relations: dict = {}

    def node(self, n):
        if n.id in self.tracker.referenced_elements['nodes'] or n.id in self.tracker.added_elements['nodes']:
            self.nodes[n.id] = NodeSerializer(n).data

    def way(self, w):
        if w.id in self.tracker.referenced_elements['ways'] or w.id in self.tracker.added_elements['ways']:
            self.ways[w.id] = WaySerializer(w).data

    def relation(self, r):
        if r.id in self.tracker.referenced_elements['relations'] or r.id in self.tracker.added_elements['relations']:
            self.relations[r.id] = RelationSerializer(r).data


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
