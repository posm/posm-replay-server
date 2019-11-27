#!/bin/bash -x

export PYTHONUNBUFFERED=1

pip3 install -r requirements.txt

celery -A posm_reolay worker --concurrency=1 -l info &

python3 manage.py runserver 0.0.0.0:6007
