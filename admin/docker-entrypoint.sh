#!/bin/bash

# Apply database migrations
echo "Apply database migrations"
python manage.py migrate

# Collect static files for whitenoise
echo "Collecting static files"
python manage.py collectstatic --noinput

# Reload any already issued trustmarks
python manage.py reload_issued_tms

# Start server
echo "Starting web server"
python manage.py runserver 0.0.0.0:8000
