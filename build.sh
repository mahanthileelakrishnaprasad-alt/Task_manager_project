#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# This line is missing and is required to fix the ModuleNotFoundError:
export PYTHONPATH=.

python manage.py collectstatic --no-input
python manage.py migrate