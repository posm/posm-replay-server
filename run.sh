#!/bin/bash

# Run docker
# check if docker-compose-prod exists
if [ -f docker-compose-prod.yml ]; then
    docker_flag=-f docker-compose-prod.yml
else
    docker_flag=
fi

docker-compose $docker_flag up -d

# This runs the pip reader that executes host command from inside docker
./scripts/pipe_reader_writer.sh &

docker-compose $docker_flag logs -f
