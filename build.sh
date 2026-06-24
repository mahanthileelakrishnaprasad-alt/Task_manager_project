#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Tell Python to look at the exact directory Render is executing from
export PYTHONPATH=$(pwd)

python manage.py collectstatic --no-input
python manage.py migrate