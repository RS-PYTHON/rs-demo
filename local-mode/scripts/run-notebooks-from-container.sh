#!/usr/bin/env bash

# Copyright 2023-2026 Airbus, CS Group
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This script is called by run-notebooks.sh to run all the notebooks from inside a docker container.

set -uo pipefail
# NOTE: -e is intentionally omitted at the top level so that individual notebook
# failures don't abort the whole script. Each subshell uses its own set -e.

# This script is run from the ci/cd
export RSPY_FROM_CICD=1

OUTPUT_DIR="/tmp/notebook-outputs"
mkdir -p "${OUTPUT_DIR}"

all_ignored=

# Arrays to track background jobs: parallel pids and their notebook paths
declare -a pids=()
declare -a pid_notebooks=()

# For each demo notebook, sorted by name
for notebook in $(find "${HOME}/notebooks" -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do
    _dirname="$(dirname "$notebook")"
    _filename="$(basename "$notebook")"
    _relative="$(realpath "$notebook" --relative-to "$HOME")"

    # For testing. Keep this line commented in git.
    # if [[ "$_relative" != "notebooks/sprints/sprintxx/yyy.ipynb" ]]; then continue; fi

    # Ignore these notebooks
    ignore=false
    while IFS= read -r line; do
        if [[ $_relative == $line ]]; then
            ignore=true
            break
        fi
    done < "/scripts/ignored-notebooks.txt"

    if [[ $ignore == true ]]; then
        all_ignored="${all_ignored:-} - '$_relative'\n"
        continue
    fi

    # Block until a slot is available (fewer than MAX_PARALLEL jobs running)
    # wait_for_slot

    # Run each notebook in a background subshell.
    # NOTE: you can add '--log-output' to view outputs.
    (
        set -e
        set -x
        cd "$_dirname"
        _outname="${_relative//\//__}"
        time papermill "${_filename}" "${OUTPUT_DIR}/${_outname}"
    ) &

    pids+=($!)
    pid_notebooks+=("$_relative")
done

# Wait for all background jobs and collect results
all_ok=
all_errors=

for i in "${!pids[@]}"; do
    pid="${pids[$i]}"
    nb="${pid_notebooks[$i]}"

    if wait "$pid"; then
        all_ok="${all_ok:-} - '$nb'\n"
    else
        all_errors="${all_errors:-} - '$nb'\n"
    fi
done

if [[ -n "$all_ok" ]]; then
    >&2 echo -e "\nNOTEBOOKS RUN SUCCESSFULLY:\n${all_ok}"
fi

if [[ -n "$all_ignored" ]]; then
    >&2 echo -e "\nIGNORED:\n${all_ignored}"
fi

if [[ -n "$all_errors" ]]; then
    >&2 echo -e "\nERRORS ON NOTEBOOKS:\n${all_errors}"
    exit 1
fi
