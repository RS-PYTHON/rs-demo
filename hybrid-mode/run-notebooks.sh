#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/..)"

# Run all the demos in hybrid mode.
# This is meant to run the demos locally, but use the services deployed on the cluster.

# Configure environment
source "${SCRIPT_DIR}/resources/jupyter-env.sh"

all_errors=

# Run each demo notebook. Use a 5' timeout for each cell.
# TODO: maybe try papermill instead of 'jupyter execute' to see verbose/progression ?
for notebook in $(find $ROOT_DIR/sprints -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do
    (set -x; time jupyter execute --timeout=300 $notebook) \
    || all_errors="${all_errors:-}  - '$(realpath $notebook --relative-to $ROOT_DIR)'\n"
done

if [[ -n "$all_errors" ]]; then
    >&2 echo -e "\nERRORS ON NOTEBOOKS:\n${all_errors}"
    exit 1
fi