# POSM Replay Tool Server

Server for pushing and managing the local changesets to OSM server.

## Getting started

### Setting up configuration

```bash
cp env_sample .env
```

### Running locally

```sh
docker-compose up
```

### Loading mock data

```
# Get data
curl -o jawalakhel.zip https://github.com/posm/posm-replay-client/files/4855795/Jawalakhel.zip
unzip jawalakhel.zip

# Copy aoi
mkdir /opt/data/aoi -p
sudo chown $USER /opt/data/aoi
mv Jawalakhel /opt/data/aoi

# Load data
docker-compose exec server bash
python3 manage.py loaddata replay_tool_data.json
rm replay_tool_data.json
```

## Deployment

Refer [Deploy Notes.md](./Deploy-Notes.md)

## API Docs

Refer [API Documentation.md](./API_Documentation.md)
