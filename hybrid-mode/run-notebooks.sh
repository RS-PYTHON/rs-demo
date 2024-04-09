#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/..)"

# Run all the demos in hybrid mode.
# This is meant to run the demos locally, but use the services deployed on the cluster.

# Configure environment
source "${SCRIPT_DIR}/resources/jupyter-env.sh"

# Run each demo notebook.
# TODO: maybe try papermill instead of 'jupyter execute' to see verbose/progression ?
for notebook in $(find $ROOT_DIR/sprints -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do
    (set -x; time jupyter execute --timeout=300 $notebook) # use a 5' timeout for each cell
done