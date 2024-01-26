#!/usr/bin/env bash
# Clear jupyter notebook outputs (useful before commiting to git)
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

for notebook in $(find "$SCRIPT_DIR"/sprints -type f -name "*.ipynb"); do
    (set -x; jupyter nbconvert --clear-output --inplace "$notebook")
done
