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
The variables that need to be set are described below. The file `env_sample`
also contains sample values for the variables.
**COPY** `env_sample` to `.env` and you are good to go.

All the other configurations can be done form the UI itself(`http://replay-tool.posm.io`)

Database settings for server:
- **DATABASE_NAME**: Need not change.
- **DATABASE_USER**: Need not change.
- **DATABASE_PASSWORD**: Need not change.

## Restarting the service
The corresponding service for replay tool is `replay-tool.service`. Make sure you restart the service whenever there are modifications in the `.env` configuration.
