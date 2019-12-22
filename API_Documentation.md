# API Documentation

## Replay Tool
**`GET /api/v1/replay-tool/`** 

This API gets the current AOI information and Replay Tool status.
Response
```
{
    "id": 1,
    "aoi": {
        "name": "Jawalakhel",
        "bounds": [
            85.31066555023207,
            27.67117097577173,
            85.32710212707534,
            27.682648488328013
        ],
        "description": "Map of jawalakhel",
        "dateCloned": "2019-12-22T09:51:04.089626",
        "totalConflictingElements": 1,
        "totalResolvedElements": 0,
        "localChangesetsCount": 6,
        "localElementsCount": {
            "waysCount": 6062,
            "nodesCount": 33939,
            "relationsCount": 49
        },
        "upstreamElementsCount": {
            "waysCount": 6082,
            "nodesCount": 33945,
            "relationsCount": 48
        }
    },
    "state": "conflicts",
    "isCurrentStateComplete": true,
    "hasErrored": false
}
```

## Triggering and re-triggering
Replay tool is in the following states in order:
- not_triggered
- gathering_changesets
- extracting_upstream_aoi
- extracting_local_aoi
- detecting_conflicts
- creating_geojsons

So, whenever the state is *not_triggered* call the following api to trigger the replay tool: 
**`POST /api/v1/trigger/`**
**NOTE**: the response is 200 even if the replay tool has been already triggered.

If in any state, error occurs, which is denoted by *hasErrored* field, call the following to retrigger replay tool:
**`POST /api/v1/re-trigger/`**

The response for both the apis is:
```
{
	"message": "Replay tool has successfully been triggered/re-triggered"
}
```

## Conflicts
When the step *creating_geojsons* is complete, one can now ask for conflicts and update and resolve them.

### List the conflicts:
`GET /api/v1/conflicts/`

```
{
    "count": 1,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 160,
            "elementId": 31232256,
            "type": "node",
            "name": "Bir Hospital"
        }
    ]
}
```

### Retrieve a particular conflict 
`GET /api/v1/conflicts/160/`

```
{
    "id": 160,
    "currentGeojson": {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [
                85.3140863,
                27.7057106
            ]
        },
        "properties": {
            "tags": [
                {
                    "k": "name",
                    "v": "Bir Hospital"
                },
                {
                    "k": "name:en",
                    "v": "Bir Hospital बीर अस्पताल प्रवेश द्वार ७"
                }
            ],
            "deleted": false,
            "visible": true
        }
    },
    "elementId": 31232256,
    "type": "node",
    "originalGeojson": {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [
                85.3140863,
                27.7057106
            ]
        },
        "properties": {
            "id": 31232256,
            "uid": 864593,
            "tags": [
                {
                    "k": "name",
                    "v": "Bir Hospital"
                },
                {
                    "k": "name:en",
                    "v": "Bir Hospital बीर अस्पताल प्रवेश द्वार ७"
                }
            ],
            "type": "node",
            "user": "Sazal(Solaris)",
            "deleted": false,
            "version": 13,
            "visible": true,
            "changeset": 64109425,
            "timestamp": "2018-11-02 11:11:02+00:00"
        }
    },
    "localGeojson": {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [
                85.3140863,
                27.7057106
            ]
        },
        "properties": {
            "id": 31232256,
            "uid": 864593,
            "tags": [
                {
                    "k": "name",
                    "v": "Bir Hospital"
                },
                {
                    "k": "name:en",
                    "v": "Bir Hospital बीर अस्पताल प्रवेश द्वार ७"
                }
            ],
            "type": "node",
            "user": "Sazal(Solaris)",
            "deleted": false,
            "version": 13,
            "visible": true,
            "changeset": 64109425,
            "timestamp": "2018-11-02 11:11:02+00:00"
        }
    },
    "upstreamGeojson": {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [
                85.3140863,
                27.7057106
            ]
        },
        "properties": {
            "id": 31232256,
            "uid": 864593,
            "tags": [
                {
                    "k": "name",
                    "v": "Bir Hospital"
                },
                {
                    "k": "name:en",
                    "v": "Bir Hospital बीर अस्पताल प्रवेश द्वार ७"
                }
            ],
            "type": "node",
            "user": "Sazal(Solaris)",
            "deleted": false,
            "version": 13,
            "visible": true,
            "changeset": 64109425,
            "timestamp": "2018-11-02 11:11:02+00:00"
        }
    },
    "isResolved": false,
    "localState": "conflicting"
}
```
The response consists of the following 4 geojsons:
- **upstreamGeojson**: Geojson corresponding to upstream changes.
- **localGeojson**: Geojson corresponding to local changes.
- **originalGeojson**: Geojson corresponding to the time when AOI was cloned into POSM.
- **currentGeojson**: Geojson corresponding to the resolved/partial-resolved conflict.

**isResolved** denotes if it has been resolved.

Note that all the data for the element resides in the *properties* key inside geoJson. And the client will patch only the values inside this key.

### Update a conflict
Send the modified values for the attributes inside the *properties* key.

`PATCH /api/v1/conflicts/update/`
Sample Request body:
```
{
    "tags": [
        {
            "k": "name",
            "v": "Bir Aspatal"
        },
        {
            "k": "name:en",
            "v": "Bir Hospital"
        }
    ],
    // nodes in the case of way
    "nodes": [
        {
          "ref": 100111
        }
    ]
}
```
### Resolve a conflict
If you intend to set the update as resolved, use the following. The body is same as for updating.
`PATCH /api/v1/conflicts/resolve/`
Sample Request body:
```
{
    "tags": [
        {
            "k": "name",
            "v": "Bir Aspatal"
        },
        {
            "k": "name:en",
            "v": "Bir Hospital"
        }
    ],
    // nodes in the case of way
    "nodes": [
        {
          "ref": 100111
        }
    ]
}
```
The response in both the cases will be the updated data of the conflicting element.
