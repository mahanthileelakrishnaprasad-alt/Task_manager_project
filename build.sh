#!/usr/bin/env bash
# exit on error
set -o errexit

# Install the Python dependencies
pip install -r requirements.txt

# Run migrations and collect static files using the right path
python taskmaster/manage.py collectstatic --no-input
python taskmaster/manage.py migrate