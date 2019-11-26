from django.db import models


class ReplayToolStat(models.Model):
    STATUS_NOT_TRIGGERRED = 'not_triggered'
    STATUS_TRIGGERRED = 'triggered'
    STATUS_GATHERING_CHANGESETS = 'gathering_changesets'
    STATUS_EXTRACTING_LOCAL_AOI = 'extracting_local_aoi'
    STATUS_EXTRACTING_UPSTREAM_AOI = 'extracting_upstream_aoi'
    STATUS_CONFLICTS = 'conflicts'
    STATUS_RESOLVED = 'resolved'
    STATUS_PUSH_CONFLICTS = 'push_conflicts'
    STATUS_PUSHED_UPSTREAM = 'pushed_upstream'

    CHOICES_STATUS = (
        (STATUS_NOT_TRIGGERRED, 'Not Triggered'),
        (STATUS_TRIGGERRED, 'Triggered'),
        (STATUS_GATHERING_CHANGESETS, 'Gathering Changesets'),
        (STATUS_EXTRACTING_LOCAL_AOI, 'Extracting Local Aoi'),
        (STATUS_EXTRACTING_UPSTREAM_AOI, 'Extracting Upstream Aoi'),
        (STATUS_CONFLICTS, 'Conflicts'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_PUSH_CONFLICTS, 'Push_conflicts'),
        (STATUS_PUSHED_UPSTREAM, 'Pushed_upstream'),
    )

    status = models.CharField(choices=CHOICES_STATUS, default=STATUS_NOT_TRIGGERRED)

    # This will help us know at which step did it errorred by looking at status
    errorred = models.BooleanField(default=False)

    def __str__(self):
        return self.status
