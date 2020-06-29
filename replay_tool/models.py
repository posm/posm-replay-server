from django.db import models, transaction
from django.contrib.postgres.fields import JSONField

from copy import deepcopy

from .utils.elements_utils import get_osm_elems_diff, replace_new_element_ids
from .utils.transformations import ChangesetsToXMLWriter

from mypy_extensions import TypedDict


class ChangeData(TypedDict):
    type: str
    action: str
    data: dict


class ReplayToolConfig(models.Model):
    osm_base_url = models.CharField(
        max_length=100,
        default="http://172.16.1.1:81",
        help_text="Enter POSM's schema://IP:port that's serving osm."
    )
    posm_db_host = models.CharField(
        max_length=100,
        default="172.16.1.1",
        help_text="POSM's IP which listens to psql connections."
    )
    posm_db_name = models.CharField(
        max_length=100,
        default="osm",
        help_text="OSM Database Name"
    )
    posm_db_user = models.CharField(
        max_length=100,
        default="osm",
        help_text="OSM Database User"
    )
    posm_db_password = models.CharField(
        max_length=100,
        default="openstreetmap",
        help_text="OSM Database password"
    )
    aoi_root = models.CharField(
        max_length=100,
        default="/aoi",
        help_text="Path inside docker mapped with host's /opt/data/aoi"
    )
    aoi_name = models.CharField(
        max_length=100,
        default="",
        help_text="Directory name of AOI which contains manifest.json and other files."
    )
    osmosis_db_host = models.CharField(
        max_length=100,
        default="172.16.1.1",
        help_text="This is probably the IP of POSM itself"
    )
    osmosis_aoi_root = models.CharField(
        max_length=100,
        default="/opt/data/aoi",
        help_text="Host AOI root location."
    )
    oauth_consumer_key = models.CharField(
        max_length=300,
        default="",
        help_text="OSM OAUTH consumer key"
    )
    oauth_consumer_secret = models.CharField(
        max_length=300,
        default="",
        help_text="OSM OAUTH consumer secret"
    )
    original_aoi_file_name = models.CharField(
        max_length=300,
        default="original_aoi.osm",
        help_text="File name for original aoi[osm file located inside aoi along with manifest json]"
    )
    overpass_api_url = models.CharField(
        max_length=100,
        default="http://overpass-api.de/api/interpreter",
        help_text="Overpass api from where upstream data is pulled"
    )
    oauth_api_url = models.CharField(
        max_length=100,
        default='https://master.apis.dev.openstreetmap.org',
        help_text="OSM oauth root api endpoint"
    )

    request_token_url = models.CharField(
        max_length=300,
        default="https://master.apis.dev.openstreetmap.org/oauth/request_token",
        help_text="OSM OAuth api endpoint for request token"
    )
    access_token_url = models.CharField(
        max_length=300,
        default="https://master.apis.dev.openstreetmap.org/oauth/access_token",
        help_text="OSM OAuth api endpoint for access token"
    )
    authorization_url = models.CharField(
        max_length=300,
        default="https://master.apis.dev.openstreetmap.org/oauth/authorize",
        help_text="OSM OAuth api endpoint for authorization"
    )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def delete(self, *args, **kwargs):
        pass


class ReplayTool(models.Model):
    """Singleton model that stores state of replay tool"""
    STATUS_NOT_TRIGGERRED = 'not_triggered'  # State 0, initial state
    STATUS_GATHERING_CHANGESETS = 'gathering_changesets'  # State 1
    STATUS_EXTRACTING_UPSTREAM_AOI = 'extracting_upstream_aoi'  # State 2
    STATUS_EXTRACTING_LOCAL_AOI = 'extracting_local_aoi'  # State 3
    STATUS_DETECTING_CONFLICTS = 'detecting_conflicts'  # State 4
    STATUS_CREATING_GEOJSONS = 'creating_geojsons'  # State 5
    STATUS_CONFLICTS = 'conflicts'  # State 6
    STATUS_RESOLVED = 'resolved'  # State 6
    STATUS_PUSH_CONFLICTS = 'pushing_conflicts'  # State 7
    STATUS_PUSHED_UPSTREAM = 'pushed_upstream'  # State 8

    CHOICES_STATUS = (
        (STATUS_NOT_TRIGGERRED, 'Not Triggered'),
        (STATUS_GATHERING_CHANGESETS, 'Gathering Changesets'),
        (STATUS_EXTRACTING_LOCAL_AOI, 'Extracting Local Aoi'),
        (STATUS_EXTRACTING_UPSTREAM_AOI, 'Extracting Upstream Aoi'),
        (STATUS_DETECTING_CONFLICTS, 'Detecting Conflicts'),
        (STATUS_CREATING_GEOJSONS, 'Creating GeoJSONs'),
        (STATUS_CONFLICTS, 'Conflicts'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_PUSH_CONFLICTS, 'Push Conflicts'),
        (STATUS_PUSHED_UPSTREAM, 'Pushed Upstream'),
    )

    state = models.CharField(
        max_length=100,
        choices=CHOICES_STATUS,
        default=STATUS_NOT_TRIGGERRED,
    )
    is_current_state_complete = models.BooleanField(default=False)

    # This will help us know at which step did it errored by looking at status
    has_errored = models.BooleanField(default=False)
    error_details = models.TextField(null=True, blank=True)

    elements_data = JSONField(default=dict)

    def __str__(self):
        return self.state

    @property
    def is_initiated(self):
        return self.state != self.STATUS_NOT_TRIGGERRED

    @classmethod
    def reset(cls, state=STATUS_NOT_TRIGGERRED):
        r, _ = cls.objects.get_or_create()
        r.state = state
        r.is_current_state_complete = True
        r.elements_data = dict()
        r.has_errored = False
        r.error_details = None
        # Delete other items
        LocalChangeSet.objects.all().delete()
        OSMElement.objects.all().delete()
        r.save()

    def set_next_state(self):
        total_steps = 6
        state_map = {i: k[0] for i, k in enumerate(self.CHOICES_STATUS)}
        rev_map = {v: k for k, v in state_map.items()}
        curr_state = self.state
        num = rev_map[curr_state]
        next_step = (num + 1) % total_steps
        self.state = state_map[next_step]
        self.save()

    def save(self, *args, **kwargs):
        # Just allow single instance
        self.pk = 1
        super().save(*args, **kwargs)


class LocalChangeSet(models.Model):
    STATUS_NOT_PROCESSED = 'not_processed'
    STATUS_PROCESSED = 'processed'

    CHOICES_STATUS = (
        (STATUS_NOT_PROCESSED, 'Not Processed'),
        (STATUS_PROCESSED, 'Processed'),
    )

    changeset_id = models.PositiveIntegerField(unique=True)
    changeset_meta = models.TextField()  # Stores xml meta
    changeset_data = models.TextField()  # Stores xml data

    status = models.CharField(
        max_length=20,
        choices=CHOICES_STATUS,
        default=STATUS_NOT_PROCESSED
    )

    def __str__(self):
        return f'Local Changeset # {self.changeset_id}'


class UpstreamChangeSet(models.Model):
    changeset_id = models.BigIntegerField(unique=True)
    is_closed = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.changeset_id} {"closed" if self.is_closed else "open"}'


class OSMElement(models.Model):
    TYPE_NODE = 'node'
    TYPE_WAY = 'way'
    TYPE_RELATION = 'relation'

    CHOICES_TYPE = (
        (TYPE_NODE, 'Node'),
        (TYPE_WAY, 'Way'),
        (TYPE_RELATION, 'Relation'),
    )

    LOCAL_STATE_ADDED = 'added'
    LOCAL_STATE_DELETED = 'deleted'
    LOCAL_STATE_MODIFIED = 'modified'
    LOCAL_STATE_REFERRING = 'referring'  # For ways/relations which refer to a conflicting node
    LOCAL_STATE_CONFLICTING = 'conflicting'

    CHOICES_LOCAL_STATE = (
        (LOCAL_STATE_ADDED, 'Added'),
        (LOCAL_STATE_DELETED, 'Deleted'),
        (LOCAL_STATE_MODIFIED, 'Modified'),
        (LOCAL_STATE_CONFLICTING, 'Conflicting'),
    )

    STATUS_RESOLVED = 'resolved'
    STATUS_PARTIALLY_RESOLVED = 'partially_resolved'
    STATUS_UNRESOLVED = 'unresolved'

    CHOICES_STATUS = (
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_PARTIALLY_RESOLVED, 'Partially Resolved'),
        (STATUS_UNRESOLVED, 'Unresolved'),
    )

    RESOLVED_FROM_THEIRS = 'theirs'
    RESOLVED_FROM_OURS = 'ours'
    RESOLVED_FROM_CUSTOM = 'custom'

    CHOICES_RESOLVED_FROM = (
        (RESOLVED_FROM_THEIRS, 'Theirs'),
        (RESOLVED_FROM_OURS, 'Ours'),
        (RESOLVED_FROM_CUSTOM, 'Custom'),
    )

    element_id = models.BigIntegerField()
    type = models.CharField(max_length=15, choices=CHOICES_TYPE)
    reffered_by = models.ForeignKey(
        'OSMElement',
        null=True,
        related_name='referenced_elements',
        on_delete=models.SET_NULL,
    )

    original_geojson = JSONField(default=dict)

    local_data = JSONField(default=dict)
    local_geojson = JSONField(default=dict)

    upstream_data = JSONField(default=dict)
    upstream_geojson = JSONField(default=dict)

    resolved_data = JSONField(default=dict, null=True, blank=True)
    resolved_from = models.CharField(max_length=25, null=True, blank=True, choices=CHOICES_RESOLVED_FROM)
    is_resolved = models.BooleanField(default=True)
    status = models.CharField(max_length=25, choices=CHOICES_STATUS)
    local_state = models.CharField(max_length=15, choices=CHOICES_LOCAL_STATE)

    class Meta:
        unique_together = ('element_id', 'type')

    def __str__(self):
        return f'{self.type.title()} {self.element_id}: {self.status}'

    @classmethod
    def get_all_local_elements(cls):
        """Returns all local elements that might even not have conflicted"""
        return cls.objects.filter(
            models.Q(
                models.Q(local_data__tags__isnull=False),
                type=cls.TYPE_NODE,
            ) |
            models.Q(
                ~models.Q(type=cls.TYPE_NODE),
            ) |
            models.Q(
                local_state=cls.LOCAL_STATE_REFERRING,
                referenced_elements__local_data__tags__isnull=True,
            )
        ).distinct()

    @classmethod
    def get_all_conflicting_elements(cls):
        """Returns elements that have been resolved as well"""
        return cls.objects.filter(
            models.Q(
                models.Q(upstream_data__tags__isnull=False) | models.Q(local_data__tags__isnull=False),
                local_state=cls.LOCAL_STATE_CONFLICTING,
                type=cls.TYPE_NODE,
            ) |
            models.Q(
                ~models.Q(type=cls.TYPE_NODE),
                local_state=cls.LOCAL_STATE_CONFLICTING,
            ) |
            models.Q(
                local_state=cls.LOCAL_STATE_REFERRING,
                referenced_elements__local_state=cls.LOCAL_STATE_CONFLICTING,
                referenced_elements__upstream_data__tags__isnull=True,
                referenced_elements__local_data__tags__isnull=True,
            )
        ).distinct()

    @classmethod
    def get_conflicting_elements(cls):
        return cls.objects.filter(
            models.Q(
                models.Q(upstream_data__tags__isnull=False) | models.Q(local_data__tags__isnull=False),
                ~models.Q(status=cls.STATUS_RESOLVED),
                local_state=cls.LOCAL_STATE_CONFLICTING,
                type=cls.TYPE_NODE,
            ) |
            models.Q(
                ~models.Q(type=cls.TYPE_NODE),
                ~models.Q(status=cls.STATUS_RESOLVED),
                local_state=cls.LOCAL_STATE_CONFLICTING,
            ) |
            models.Q(
                ~models.Q(referenced_elements__status=cls.STATUS_RESOLVED),
                local_state=cls.LOCAL_STATE_REFERRING,
                referenced_elements__local_state=cls.LOCAL_STATE_CONFLICTING,
                referenced_elements__upstream_data__tags__isnull=True,
                referenced_elements__local_data__tags__isnull=True,
            )
        ).distinct()

    @classmethod
    def get_partially_resolved_elements(cls):
        return cls.objects.filter(
            models.Q(
                models.Q(upstream_data__tags__isnull=False),
                status=cls.STATUS_PARTIALLY_RESOLVED,
                local_state=cls.LOCAL_STATE_CONFLICTING,
                type=cls.TYPE_NODE,
            ) |
            models.Q(
                ~models.Q(type=cls.TYPE_NODE),
                status=cls.STATUS_PARTIALLY_RESOLVED,
                local_state=cls.LOCAL_STATE_CONFLICTING,
            ) |
            models.Q(
                referenced_elements__status=cls.STATUS_PARTIALLY_RESOLVED,
                local_state=cls.LOCAL_STATE_REFERRING,
                referenced_elements__local_state=cls.LOCAL_STATE_CONFLICTING,
                referenced_elements__upstream_data__tags__isnull=True,
            )
        ).distinct()

    @classmethod
    def get_resolved_elements(cls):
        return cls.objects.filter(
            models.Q(
                models.Q(upstream_data__tags__isnull=False),
                local_state=cls.LOCAL_STATE_CONFLICTING,
                status=cls.STATUS_RESOLVED,
                type=cls.TYPE_NODE,
            ) |
            models.Q(
                ~models.Q(type=cls.TYPE_NODE),
                status=cls.STATUS_RESOLVED,
                local_state=cls.LOCAL_STATE_CONFLICTING,
            ) |
            models.Q(
                local_state=cls.LOCAL_STATE_REFERRING,
                # TODO: the following logic might not work for foreign key
                referenced_elements__local_state=cls.LOCAL_STATE_CONFLICTING,
                referenced_elements__status=cls.STATUS_RESOLVED,
                referenced_elements__upstream_data__tags__isnull=True,
            )
        ).distinct()

    @classmethod
    def get_added_elements(cls, type=None):
        typefilter = {'type': type} if type else {}
        return cls.objects.filter(
            local_state=cls.LOCAL_STATE_ADDED,
            **typefilter,
        )

    @classmethod
    @transaction.atomic
    def create_multiple_local_aoi_data(cls, type, local_aoi_pairs):
        for loc, aoi in local_aoi_pairs:
            cls.objects.create(
                element_id=loc['id'],
                type=type,
                local_data=loc,
                upstream_data=aoi,
            )

    def get_osm_change_data(self) -> ChangeData:
        """
        Returns change data(create, modify or delete)
        And calculates the diff, and the version to be sent
        """
        change_data: ChangeData = {'type': self.type, 'action': '', 'data': {}}

        resolved_data = deepcopy(self.resolved_data)
        # Pop referenced nodes/ways/relations present in resolved_data, they should
        # be resolved at this point
        resolved_data.pop('conflicting_nodes', None)
        resolved_data.pop('conflicting_ways', None)  # NOTE: this is not present at the moment
        resolved_data.pop('conflicting_relations', None)  # NOTE: this is not present at the moment

        original_data = self.original_geojson.get('properties', {})
        if self.local_state == self.LOCAL_STATE_ADDED:
            change_data['action'] = 'create'
            change_data['data'] = {k: v for k, v in self.local_data.items()}
            # Set version to 1
            change_data['data']['version'] = 1
        elif self.local_state == self.LOCAL_STATE_DELETED:
            change_data['action'] = 'delete'
            change_data['data'] = {k: v for k, v in self.local_data.items()}
            change_data['data']['id'] = self.element_id  # Just in case id is not present
            # Set version to 1 greater than upstream version
            change_data['data']['version'] = self.upstream_data['version'] + 1
        elif self.local_state == self.LOCAL_STATE_MODIFIED:
            change_data['action'] = 'modify'
            change_data['data'] = get_osm_elems_diff(self.local_data, original_data)
            # diff won't have id, so insert id
            change_data['data']['id'] = self.element_id
            # Set version to 1 greater than upstream version
            change_data['data']['version'] = self.upstream_data['version'] + 1
        elif self.local_state == self.LOCAL_STATE_CONFLICTING:
            diff = get_osm_elems_diff(resolved_data, original_data)
            action = 'delete' if diff.get('deleted') else 'modify'
            change_data['action'] = action
            change_data['data'] = diff
            # diff won't have id, so insert id
            change_data['data']['id'] = self.element_id
            # Set version to 1 greater than upstream version
            change_data['data']['version'] = self.upstream_data['version'] + 1
        else:
            raise Exception(f"Invalid value 'f{self.local_state}' for local state")

        if self.type == 'node':
            # The location info is either the local location data or location data
            # in resolved data. The former is the case when it is just modified
            # and no conflict with upstream. The later is the case when there is conflict
            location = change_data['data'].pop('location', None)
            if location:
                change_data['data']['lat'] = location['lat']
                change_data['data']['lon'] = location['lon']
            # Add lat/lon. In db they are inside location dict, for changeset, take them out.
            if resolved_data.get('location'):
                change_data['data']['lat'] = resolved_data['location']['lat']
                change_data['data']['lon'] = resolved_data['location']['lon']
        return change_data

    @classmethod
    def get_upstream_changeset(cls, changeset_id):
        changeset_writer = ChangesetsToXMLWriter()
        # Get added elements
        added_nodes = cls.get_added_elements('node')
        added_ways = cls.get_added_elements('way')
        added_relations = cls.get_added_elements('relation')

        # Map ids, map of locally created elements ids and ids to be sent to upstream(negative values)
        # The mapped ids will be used wherever the elements are referenced
        new_nodes_ids_map = {x.element_id: -(i + 1) for i, x in enumerate(added_nodes)}
        new_ways_ids_map = {x.element_id: -(i + 1) for i, x in enumerate(added_ways)}
        new_relations_ids_map = {x.element_id: -(i + 1) for i, x in enumerate(added_relations)}

        def _write_change(element):
            changeset_data = element.get_osm_change_data()
            # The data does not have locally added elements ids set to negative
            # So replace ids by negative ids if added
            changeset_data = replace_new_element_ids(
                changeset_data,
                new_nodes_ids_map,
                new_ways_ids_map,
                new_relations_ids_map,
            )
            changeset_data['data']['changeset'] = changeset_id
            changeset_writer.add_change(changeset_data)

        to_send_elements = cls.objects.filter(
            ~models.Q(local_state=OSMElement.LOCAL_STATE_REFERRING),
            ~models.Q(status=OSMElement.STATUS_UNRESOLVED),
        )
        # First add nodes
        for element in to_send_elements.filter(type=cls.TYPE_NODE):
            _write_change(element)

        # Add ways
        for element in to_send_elements.filter(type=cls.TYPE_WAY):
            _write_change(element)

        # Add Relation
        for element in to_send_elements.filter(type=cls.TYPE_RELATION):
            _write_change(element)

        return changeset_writer.get_xml()
