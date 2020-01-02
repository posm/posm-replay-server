from django.db import models, transaction
from django.contrib.postgres.fields import JSONField

from .utils.common import get_osm_elems_diff

from mypy_extensions import TypedDict


class ChangeData(TypedDict):
    type: str
    action: str
    data: dict


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

    elements_data = JSONField(default=dict)

    def __str__(self):
        return self.status

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
    is_resolved = models.BooleanField(default=True)
    status = models.CharField(max_length=25, choices=CHOICES_STATUS)
    local_state = models.CharField(max_length=15, choices=CHOICES_LOCAL_STATE)

    class Meta:
        unique_together = ('element_id', 'type')

    def __str__(self):
        return f'{self.type.title()} {self.element_id}: {self.status}'

    @classmethod
    def get_all_conflicting_elements(cls):
        """Returns elements that have been resolved as well"""
        return cls.objects.filter(
            models.Q(
                models.Q(upstream_data__tags__isnull=False),
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
            )
        ).distinct()

    @classmethod
    def get_conflicting_elements(cls):
        return cls.objects.filter(
            models.Q(
                models.Q(upstream_data__tags__isnull=False),
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

        original_data = self.original_geojson.get('properties', {})
        if self.local_state == self.LOCAL_STATE_ADDED:
            change_data['action'] = 'create'
            change_data['data'] = {k: v for k, v in self.local_data.items() if k != 'location'}
            # Set version to 1
            change_data['data']['version'] = 1
        elif self.local_state == self.LOCAL_STATE_DELETED:
            change_data['action'] = 'delete'
            change_data['data'] = {k: v for k, v in self.local_data.items() if k != 'location'}
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
            diff = get_osm_elems_diff(self.resolved_data, original_data)
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
            change_data['data'].pop('location', None)
            # Add lat/lon. In db they are inside location dict, for changeset, take them out.
            change_data['data']['lat'] = self.local_data['location']['lat']
            change_data['data']['lon'] = self.local_data['location']['lon']
        return change_data
