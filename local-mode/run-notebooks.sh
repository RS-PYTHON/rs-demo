#!/usr/bin/env bash

# Run all the notebooks using docker containers

set -euo pipefail

# Call the health endpoint until it returns a status code OK
wait_for_service() {

    port="$1"
    health="$2"

    local i=0
    while [[ ! $(set -x; curl "localhost:$port/$health" 2>/dev/null) ]]; do
        sleep 2
        i=$((i+1)); ((i>=20)) && >&2 echo "Error reaching 'localhost:$port/$health'" && exit 1
    done
    return 0
}
# Same ports as in docker-compose.yml
wait_for_service 8001 "health" # adgs
wait_for_service 8002 "health" # cadip
wait_for_service 8003 "catalog/_mgmt/health" # catalog
wait_for_service 8006 "health" # edrs
wait_for_service 8888 "login" # jupyter

# Run the notebooks from the jupyter service from the docker-compose.
set -x;
docker exec --user=root jupyter /scripts/run-notebooks-from-container.sh
