#!/usr/bin/env bash
# Clear jupyter notebook outputs (useful before commiting to git)
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/..)"

# For each demo notebook
for notebook in $(find $ROOT_DIR/sprints -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do

    # Run the notebook from a container, in the same network than the docker-compose,
    # with the same options than the jupyter service in the docker-compose.
    # Read the environment variables before running the notebook.
    (set -x; 
        docker run --rm \
            --network stac-fastapi-network \
            -v $ROOT_DIR:$ROOT_DIR \
            -v rspy-demo_rspy_working_dir:/rspy/working/dir \
            jupyter/minimal-notebook \
            bash -c "source ${ROOT_DIR}/resources/.env && jupyter execute $notebook"
    )
done