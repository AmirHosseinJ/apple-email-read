#!/bin/sh
set -eu

echo "Applying database migrations..."
python manage.py migrate --noinput

if [ "$#" -eq 0 ]; then
    set -- gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers 2 \
        --timeout 60
fi

exec "$@"
