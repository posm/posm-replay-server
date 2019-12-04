#!/bin/bash

# This runs the pip reader that executes host command from inside docker
./scripts/pipe_reader_writer.sh &

#  $1 can contain -d

# Run docker
# check if docker-compose-prod exists
if [ -f docker-compose-prod.yml ]; then
    docker-compose -f docker-compose-prod.yml up  $1
else
    docker-compose up $1
fi
