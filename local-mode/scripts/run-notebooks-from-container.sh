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

set -euo pipefail

# This script is run from the ci/cd
export RSPY_FROM_CICD=1

OUTPUT_DIR="/tmp/notebook-outputs"
mkdir -p "${OUTPUT_DIR}"

# Run papermill with the IPC kernel transport instead of the default TCP one.
# The kernel runs locally anyway, and over TCP ipykernel logs a warning
# because the communication is not encrypted.
# The IPC socket files go to a temporary directory: by default they are created
# in the notebook directory, and notebooks that upload their directory fail on them.
# When the error is not saved in the output notebook, e.g. when the kernel died,
# save it in a '<output notebook>.error.txt' file, for the CI/CD report
# (RS-PYTHON/actions report-notebooks).
run_papermill() {
    python - "$@" <<'PYTHON'
import os
import sys
import tempfile
import traceback

import papermill
from papermill.exceptions import PapermillExecutionError
from traitlets.config import Config

with tempfile.TemporaryDirectory() as ipc_dir:
    config = Config(KernelManager={"transport": "ipc", "ip": os.path.join(ipc_dir, "kernel")})
    try:
        papermill.execute_notebook(sys.argv[1], sys.argv[2], config=config)
    except PapermillExecutionError:
        raise  # the error is saved in the output notebook
    except Exception as exception:
        with open(f"{sys.argv[2]}.error.txt", "w", encoding="utf-8") as error_file:
            error_file.write("".join(traceback.format_exception_only(exception)))
        raise
PYTHON
}

all_ok=
all_errors=
all_ignored=

# For each demo notebook, sorted by name
for notebook in $(find "${HOME}/notebooks" -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do

    _dirname="$(dirname $notebook)"
    _filename="$(basename $notebook)"
    _relative="$(realpath $notebook --relative-to $HOME)"

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
        all_ignored="${all_ignored:-}  - '$_relative'\n"
        continue
    fi

    # Run the notebook in a new shell.
    # In case of error, save the notebook path relative to the root project.
    # NOTE: you can add '--log-output' to view outputs.
    _outname="${_relative//\//__}"
    (set -x && cd "${_dirname}" && time run_papermill "${_filename}" "${OUTPUT_DIR}/${_outname}") && \
    all_ok="${all_ok:-}  - '$_relative'\n" || \
    all_errors="${all_errors:-}  - '$_relative'\n"
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
