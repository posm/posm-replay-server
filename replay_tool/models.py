from django.db import models, transaction
from django.contrib.postgres.fields import JSONField


class ReplayTool(models.Model):
    """Singleton model that stores state of replay tool"""
    STATUS_NOT_TRIGGERRED = 'not_triggered'  # Step 0, initial state
    STATUS_GATHERING_CHANGESETS = 'gathering_changesets'  # Step 1
    STATUS_EXTRACTING_UPSTREAM_AOI = 'extracting_upstream_aoi'  # Step 2
    STATUS_EXTRACTING_LOCAL_AOI = 'extracting_local_aoi'  # Step 3
    STATUS_DETECTING_CONFLICTS = 'detecting_conflicts'  # Step 4
    STATUS_CREATING_GEOJSONS = 'creating_geojsons'  # Step 5
    STATUS_CONFLICTS = 'conflicts'
    STATUS_RESOLVED = 'resolved'
    STATUS_PUSH_CONFLICTS = 'push_conflicts'
    STATUS_PUSHED_UPSTREAM = 'pushed_upstream'

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
        ConflictingNode.objects.all().delete()
        ConflictingWay.objects.all().delete()
        ConflictingRelation.objects.all().delete()
        r.save()

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


class ConflictingOSMElement(models.Model):
    LOCAL_ACTION_ADDED = 'added'
    LOCAL_ACTION_DELETED = 'deleted'
    LOCAL_ACTION_MODIFIED = 'modified'

    CHOICES_LOCAL_ACTION = (
        (LOCAL_ACTION_ADDED, 'Added'),
        (LOCAL_ACTION_DELETED, 'Deleted'),
        (LOCAL_ACTION_MODIFIED, 'Modified'),
    )
    local_data = JSONField(default=dict)
    upstream_data = JSONField(default=dict)
    resolved_data = JSONField(default=dict, null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    local_action = models.CharField(
        max_length=15,
        choices=CHOICES_LOCAL_ACTION,
        default=LOCAL_ACTION_MODIFIED,
    )

    class Meta:
        abstract = True


class ConflictingNode(ConflictingOSMElement):
    node_id = models.BigIntegerField(unique=True)

    def __str__(self):
        status = 'Resolved' if self.is_resolved else 'Conflicting'
        return f'Node {self.node_id}: {status}'

    @classmethod
    @transaction.atomic
    def create_multiple_local_aoi_data(cls, local_aoi_pairs, **kwargs):
        for loc, aoi in local_aoi_pairs:
            cls.objects.create(
                node_id=loc['id'],
                local_data=loc,
                upstream_data=aoi,
                **kwargs
            )

    @property
    def local_geojson(self):
        # GeoJSON is cached
        if not hasattr(self, '_local_geojson'):
            self._local_geojson = get_node_geojson(self.local_data)
        return self._geojson

    @property
    def upstream_geojson(self):
        # GeoJSON is cached
        if not hasattr(self, '_upstream_geojson'):
            self._local_geojson = get_node_geojson(self.upstream_data)
        return self._geojson


class ConflictingWay(ConflictingOSMElement):
    way_id = models.BigIntegerField(unique=True)

    def __str__(self):
        status = 'Resolved' if self.resolved else 'Conflicting'
        return f'Way {self.way_id}: {status}'

    @classmethod
    @transaction.atomic
    def create_multiple_local_aoi_data(cls, local_aoi_pairs, **kwargs):
        for loc, aoi in local_aoi_pairs:
            cls.objects.create(
                way_id=loc['id'],
                local_data=loc,
                upstream_data=aoi,
                **kwargs
            )

    @property
    def local_geojson(self):
        # GeoJSON is cached
        if not hasattr(self, '_local_geojson'):
            self._local_geojson = get_way_geojson(self.local_data)
        return self._geojson

    @property
    def upstream_geojson(self):
        # GeoJSON is cached
        if not hasattr(self, '_upstream_geojson'):
            self._local_geojson = get_way_geojson(self.upstream_data)
        return self._geojson


class ConflictingRelation(ConflictingOSMElement):
    relation_id = models.BigIntegerField(unique=True)

    def __str__(self):
        status = 'Resolved' if self.resolved else 'Conflicting'
        return f'Relation {self.node_id}: {status}'

    @classmethod
    @transaction.atomic
    def create_multiple_local_aoi_data(cls, local_aoi_pairs, **kwargs):
        for loc, aoi in local_aoi_pairs:
            cls.objects.create(
                relation_id=loc['id'],
                local_data=loc,
                upstream_data=aoi,
                **kwargs
            )

    @property
    def local_geojson(self):
        # GeoJSON is cached
        if not hasattr(self, '_local_geojson'):
            self._local_geojson = get_relation_geojson(self.local_data)
        return self._geojson

    @property
    def upstream_geojson(self):
        # GeoJSON is cached
        if not hasattr(self, '_upstream_geojson'):
            self._local_geojson = get_relation_geojson(self.upstream_data)
        return self._geojson


def get_node_geojson(data):
    if not data:
        return {}
    location = data['location']
    return {
        'type': 'Feature',
        'geometry': {
            'type': 'Point',
            'coordinates': [location['lat'], location['lon']],
        },
        'properties': {
            k: v for k, v in data.items() if k != 'location'
        }
    }


def get_way_geojson(data):
    if not data:
        return {}
    return {}


def get_relation_geojson(data):
    if not data:
        return {}
    return {}
