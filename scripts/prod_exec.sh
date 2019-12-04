#!/bin/bash -x

export PYTHONUNBUFFERED=1

pip3 install -r requirements.txt

python3 manage.py migrate --no-input

# Create pipe to read result
# TODO: set this in env var
rm osmosis_result_reader.fifo 2>/dev/null
mkfifo osmosis_result_reader.fifo

celery -A posm_reolay worker --concurrency=1 -l info &

python3 manage.py runserver 0.0.0.0:6007
