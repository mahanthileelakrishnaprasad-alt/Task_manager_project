#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

echo "=== DEBUGGING PATHS ==="
echo "Current directory: $(pwd)"
echo "Listing contents of current directory:"
ls -la
echo "======================="

# Set the path explicitly to the current folder
export PYTHONPATH=$(pwd)

python manage.py collectstatic --no-input
python manage.py migrate