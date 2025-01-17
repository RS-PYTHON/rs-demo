#!/usr/bin/env bash

# This script is called by run-notebooks.sh to run all the notebooks from inside a docker container.

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/../..)"

# We are always on local mode
export RSPY_LOCAL_MODE=1

# Read environment variables from the .env file
source ${ROOT_DIR}/local-mode/.env

all_ok=
all_errors=

# For each demo notebook, sorted by name
for notebook in $(find $ROOT_DIR/notebooks -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do

    _dirname="$(dirname $notebook)"
    _filename="$(basename $notebook)"
    _relative="$(realpath $notebook --relative-to $ROOT_DIR)"

    # Run the notebook in a new shell.
    # In case of error, save the notebook path relative to the root project.
    (set -x && cd "$_dirname" && time papermill "$_filename" /tmp/out.ipynb) && \
    all_ok="${all_ok:-}  - '$_relative'\n" || \
    all_errors="${all_errors:-}  - '$_relative'\n"
done

if [[ -n "$all_ok" ]]; then
    >&2 echo -e "\nNOTEBOOKS RUN SUCCESSFULLY:\n${all_ok}"
fi

if [[ -n "$all_errors" ]]; then
    >&2 echo -e "\nERRORS ON NOTEBOOKS:\n${all_errors}"
    exit 1
fi
