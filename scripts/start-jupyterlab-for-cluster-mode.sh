#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/..)"

# Starts a local instance of jupyter lab. 
# This is meant to run the demos locally, but use the services deployed on the cluster.

# Check that jupyter is installed locally
if ! jupyter lab --version >/dev/null 2>&1; then
    >&2 echo "Install jupyter lab with 'pip install jupyterlab'"
    exit 1
fi

# As we use the cluster mode, we can set local mode to false
export RSPY_LOCAL_MODE=0

# Set the URLs to use in environment variables
export RSPY_WEBSITE="https://dev-rspy.esa-copernicus.eu"
export RSPY_WEBSITE_SWAGGER="${RSPY_WEBSITE}/docs"

# We need an API key to authenticate to the HTTP endpoints
if [[ -z "${RSPY_APIKEY:-}" ]]; then
    >&2 echo "Generate an API key from '$RSPY_WEBSITE_SWAGGER' then run 'export RSPY_APIKEY=your_api_key'"
    exit 1
fi

# Run jupyter lab on the 'sprints' directory. 
# Run Ctrl-C to exit.
jupyter lab "${ROOT_DIR}/sprints"

