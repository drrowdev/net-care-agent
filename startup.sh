#!/bin/bash
gunicorn --bind 0.0.0.0:8000 --timeout 300 --workers 1 app:app