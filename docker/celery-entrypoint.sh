#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
    set -- celery -A config worker \
        --loglevel info \
        --concurrency 1
fi

exec "$@"
