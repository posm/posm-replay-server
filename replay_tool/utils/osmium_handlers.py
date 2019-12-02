import osmium


class AOIHandler(osmium.SimpleHandler):
    """
    Stores AOI elements as keys values pair.
    """
    def __init__(self):
        super().__init__()
        self.nodes: dict = {}
        self.ways: dict = {}
        self.relations: dict = {}

    def node(self, n):
        self.nodes[n.id] = n

    def way(self, w):
        self.ways[w.id] = w

    def relation(self, r):
        self.relations[r.id] = r


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

    def node(self, n):
        if n.version == 1:
            self.added_elements['nodes'].add(n.id)
        elif not n.visible:
            # If not visible and exists in self.added_elements,
            # remove it from added elements. Else, add as deleted and referenced
            if n.id not in self.added_elements['nodes']:
                self.deleted_elements['nodes'].add(n.id)
                self.referenced_elements['nodes'].add(n.id)
            else:
                self.added_elements['nodes'].remove(n.id)
        else:
            # Add to modified elements only if it is not in added elements,
            # Because we have to flag it as added node
            # Once locally added, it does not matter if it is modified
            if n.id not in self.added_elements['nodes']:
                self.modified_elements['nodes'].add(n.id)
                self.referenced_elements['nodes'].add(n.id)
