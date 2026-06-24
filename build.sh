#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Look one level up so Python can find the taskmaster folder
export PYTHONPATH=$PYTHONPATH:..

python manage.py collectstatic --no-input
python manage.py migrate