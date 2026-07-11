#!/bin/bash
set -eu
exec gunicorn --bind "0.0.0.0:${PORT:-8000}" --timeout 300 --graceful-timeout 30 --workers 1 app:app
