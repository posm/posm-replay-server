#!/bin/bash -x

export PYTHONUNBUFFERED=1

pipenv install -r requirements.txt

# Create pipe to read result
# TODO: set this in env var
rm osmosis_result_reader.fifo 2>/dev/null
mkfifo osmosis_result_reader.fifo

pipenv run celery -A posm_reolay worker --concurrency=1 -l info &

pipenv run python3 manage.py runserver 0.0.0.0:6007
