#!/usr/bin/env bash

# Run all the notebooks using docker containers

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/..)"

# By default, we are on local mode
[[ -z "${RSPY_LOCAL_MODE:-}" ]] && export RSPY_LOCAL_MODE=1

# On local mode
if [[ "$RSPY_LOCAL_MODE" == "1" ]]; then

    # Call the health endpoint until it returns a status code OK
    wait_for_service() {

        port="$1"
        health="$2"
        
        local i=0
        while [[ ! $(set -x; curl "localhost:$port/$health" 2>/dev/null) ]]; do
            sleep 2
            i=$((i+1)); ((i>=10)) && >&2 echo "Error reaching 'localhost:$port/$health'" && exit 1
        done
        return 0
    }
    # Same ports as in docker-compose.yml
    wait_for_service 8001 "health" # adgs
    wait_for_service 8002 "health" # cadip
    wait_for_service 8003 "_mgmt/ping" # catalog
fi

all_errors=

# For each demo notebook
for notebook in $(find $ROOT_DIR/sprints -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do

    # The 'items' table from catalog has to be truncated before running 
    # a new notebook (even if the demo is not using the catalog)
    # If this isn't done, the demos that are using the catalog and buckets will fail 
    # the second time they are run, without shutting down the containers
    # (set -x; 
    #     docker exec catalog-db psql -U postgres -d catalog -c "TRUNCATE items"
    # )
    #
    # Julien's note: instead, clean the catalog at the start of each demo using rspy code and http endpoints.
    # When running on the cluster, we can't clean the database deployed on the cluster.

    # Run the notebook from a container, in the same network than the docker-compose,
    # with the same options than the jupyter service in the docker-compose.
    # Read the environment variables before running the notebook.
    (set -x; 
        time docker run --rm \
            --network rspy-network \
            -e RSPY_LOCAL_MODE \
            -v $ROOT_DIR:$ROOT_DIR \
            -v rspy-demo_rspy_working_dir:/rspy/working/dir \
            jupyter/minimal-notebook \
            bash -c "source ${ROOT_DIR}/local-mode/.env && jupyter execute $notebook") \
    || all_errors="${all_errors:-}  - '$(realpath $notebook --relative-to $ROOT_DIR)'\n"
done

if [[ -n "$all_errors" ]]; then
    >&2 echo -e "\nERRORS ON NOTEBOOKS:\n${all_errors}"
fi