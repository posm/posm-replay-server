from django.db import models


class ReplayTool(models.Model):
    """Singleton model that stores state of replay tool"""
    STATUS_NOT_TRIGGERRED = 'not_triggered'
    STATUS_GATHERING_CHANGESETS = 'gathering_changesets'
    STATUS_EXTRACTING_LOCAL_AOI = 'extracting_local_aoi'
    STATUS_EXTRACTING_UPSTREAM_AOI = 'extracting_upstream_aoi'
    STATUS_CONFLICTS = 'conflicts'
    STATUS_RESOLVED = 'resolved'
    STATUS_PUSH_CONFLICTS = 'push_conflicts'
    STATUS_PUSHED_UPSTREAM = 'pushed_upstream'

    CHOICES_STATUS = (
        (STATUS_NOT_TRIGGERRED, 'Not Triggered'),
        (STATUS_GATHERING_CHANGESETS, 'Gathering Changesets'),
        (STATUS_EXTRACTING_LOCAL_AOI, 'Extracting Local Aoi'),
        (STATUS_EXTRACTING_UPSTREAM_AOI, 'Extracting Upstream Aoi'),
        (STATUS_CONFLICTS, 'Conflicts'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_PUSH_CONFLICTS, 'Push_conflicts'),
        (STATUS_PUSHED_UPSTREAM, 'Pushed_upstream'),
    )

    status = models.CharField(
        max_length=20,
        choices=CHOICES_STATUS,
        default=STATUS_NOT_TRIGGERRED,
    )
    current_state_completed = models.BooleanField(default=False)

    # This will help us know at which step did it errorred by looking at status
    errorred = models.BooleanField(default=False)

    def __str__(self):
        return self.status

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
