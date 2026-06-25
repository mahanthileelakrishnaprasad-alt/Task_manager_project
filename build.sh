#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
python taskmaster/manage.py collectstatic --no-input
python taskmaster/manage.py migrate
