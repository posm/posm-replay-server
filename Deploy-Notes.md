## POSM Replay Server deploy notes

**POSM Replay Server** is a django app running inside a docker container. It
runs on port `6007` inside the container and the same port is also exposed
outside. In a posm instance, it can be accessed from browser in the address
`replay-tool.posm.io`. 

The **docker-compose** configurations are located at `/opt/replay_tool/posm-replay-server/docker-compose.yml`.
The host directory `/opt/data/aoi/` is mapped to the directory `/aoi` inside docker environment. 


**Posm Replay Client** does not need speial configuration. It is automatically
set up from posm-build iso. 


When the POSM runs in NUC, the server is up and running along with the client,
which is just a bunch of static html/js files. However, some information about
AOI, endpoints from where local changesets are collected and database
information need to be configured. The configuration variables reside as
environment variables in the file `/opt/replay-tool/posm-replay-server/.env`.
The variables that need to be set are described below. The file `sample_env`
also contains sample values for the variables. 

**NOTE:** Just change the value for AOI_NAME above which is the name of directory for aoi inside `/opt/data/aoi/` directory.
Other fields need not be changed.

- **OSM_BASE_URL**: This is the local osm endpoint where the server makes calls to gather the changesets. The value should be POSM's IP with port 81.
- **POSM_DB_HOST**: This is used to make local osm database queries to get the `first changeset id`. It's value is also POSM's IP.
- **POSM_DB_NAME**: The database name where local osm data resides. The value is `osm` which should already be set.
- **POSM_DB_USER**: The database username. The value is `osm` which should already be set.
- **POSM_DB_PASSWORD**: The database password. This should be the default password for apidb and needs to be set
- **AOI_ROOT**: This is the directory inside docker environment where our AOI data resides. The value is `/aoi` and it need not be changed.
- **AOI_NAME**: The name of the AOI directory. For example `/opt/data/aoi` can have multiple AOIS, this value should be the one we are interested to resolve conflicts in.
- **ORIGINAL_AOI_FILE_NAME**: The file name of the original aoi. It's path is `/opt/data/aoi/<AOI_NAME>/<ORIGINAL_AOI_FILE_NAME>`.
- **OSMOSIS_DB_HOST**: To keep the docker container size small, `osmosis` is not installed in the container, but accessed from within the container. The value is the ip of POSM.
- **OSMOSIS_AOI_ROOT**: Since osmosis runs on host instead of docker, this values is `/opt/data/aoi`. This is used to extract referenced osm elements from local and upstream osm files.

Database settings for server:
- **DATABASE_NAME**: Need not change.
- **DATABASE_USER**: Need not change.
- **DATABASE_PASSWORD**: Need not change.

**NOTE:** Change the following values appropriately.

OAuth Config:
- **OAUTH_CONSUMER_KEY**: OAuth app Consumer Key
- **OAUTH_CONSUMER_SECRET**: OAuth app Secret Key
- **OAUTH_API_URL**: OSM OAuth API endpoint

- **REQUEST_TOKEN_URL**: <OSM_API_URL>/oauth/request_token
- **ACCESS_TOKEN_URL**: <OSM_API_URL>/oauth/access_token
- **AUTHORIZE_URL**: <OSM_API_URL>/oauth/authorize

## Restarting the service
The corresponding service for replay tool is `replay-tool.service`. Make sure you restart the service whenever there are modifications in the `.env` configuration.
