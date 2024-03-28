#!/usr/bin/env bash

# Run all the notebooks using docker containers

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/..)"

# before connecting to the catalog database, some time isneeded for the database to start
# fix github error: failed: FATAL:  the database system is starting up
sleep 10

# For each demo notebook
for notebook in $(find $ROOT_DIR/sprints -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do

    # The 'items' table from catalog has to be truncated before running 
    # a new notebook (even if the demo is not using the catalog)
    # If this isn't done, the demos that are using the catalog and buckets will fail 
    # the second time they are run, without shutting down the containers
    (set -x; 
        docker exec catalog-db psql -U postgres -d catalog -c "TRUNCATE items"
    )

    # Run the notebook from a container, in the same network than the docker-compose,
    # with the same options than the jupyter service in the docker-compose.
    # Read the environment variables before running the notebook.
    (set -x; 
        docker run --rm \
            --network rspy-network \
            -v $ROOT_DIR:$ROOT_DIR \
            -v rspy-demo_rspy_working_dir:/rspy/working/dir \
            jupyter/minimal-notebook \
            bash -c "source ${ROOT_DIR}/resources/.env && jupyter execute $notebook"
    )
done