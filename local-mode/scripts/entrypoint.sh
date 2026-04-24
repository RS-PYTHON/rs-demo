#!/bin/sh
set -e
APP_MODULE=${1}
python /home/user/.config/export_vars.py /home/user/.config/rs-server.yaml

while IFS= read -r line; do
  export "$line"
done < .env2

exec python -m uvicorn "$APP_MODULE" \
  --host 0.0.0.0 --port 8000 --reload
