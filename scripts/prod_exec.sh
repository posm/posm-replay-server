#!/bin/bash -x

export PYTHONUNBUFFERED=1

python3 manage.py migrate --no-input

# Create pipe to read result
# TODO: set this in env var
# rm osmosis_result_reader.fifo 2>/dev/null
# mkfifo osmosis_result_reader.fifo

# celery -A posm_replay worker  --concurrency=1 -l info &
# NOTE: Run celery manually
# python3 manage.py celery &

uwsgi --ini /code/scripts/uwsgi.ini
