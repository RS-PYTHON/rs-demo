#!/usr/bin/env bash
# Clear jupyter notebook outputs (useful before commiting to git)
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/..)"

for notebook in $(find $ROOT_DIR/sprints -type f -name "*.ipynb" -not -path "*checkpoints*" | sort); do
    (set -x; jupyter nbconvert --clear-output --inplace "$notebook")
done
