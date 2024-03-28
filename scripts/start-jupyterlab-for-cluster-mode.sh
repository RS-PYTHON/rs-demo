#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR="$(realpath $SCRIPT_DIR/..)"

# Start a local instance of jupyter lab. 
# This is meant to run the demos locally, but use the services deployed on the cluster.

# Check that jupyter is installed locally
if ! jupyter lab --version >/dev/null 2>&1; then
    >&2 echo "Install jupyter lab with 'pip install jupyterlab'"
    exit 1
fi

# We also need rs-client libraries, check that it's installed
if ! python -c "import rs_workflows" >/dev/null 2>&1; then
    >&2 echo -e "Install rs-client libraries with \n"\
"  'pip install rs_client_libraries-*.whl' (to install a static release) or \n"\
"  'pip install -e /path/to/local/project/rs-client-libraries' (to install dynamically from the source code)"
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

# We need the S3 bucket info. Try to read them from the local .s3cfg file.
s3cfg="${HOME}/.s3cfg"
if [[ -z "${S3_ACCESSKEY:-}" || -z "${S3_SECRETKEY:-}" || -z "${S3_ENDPOINT:-}" || -z "${S3_REGION:-}" ]]; then
    if [[ -f "$s3cfg" ]]; then
        echo "Read S3 information from '$s3cfg'"        

        # Extract field value from the file
        read_s3cfg() {
            awk -F = "/$1/ "'{print $2}' "$s3cfg" | tr -d '[:space:]'
        }
        [[ -z "${S3_ACCESSKEY:-}" ]] && export S3_ACCESSKEY=$(read_s3cfg access_key)
        [[ -z "${S3_SECRETKEY:-}" ]] && export S3_SECRETKEY=$(read_s3cfg secret_key)
        [[ -z "${S3_ENDPOINT:-}" ]] && export S3_ENDPOINT=$(read_s3cfg host_bucket)
        [[ -z "${S3_REGION:-}" ]] && export S3_REGION=$(read_s3cfg bucket_location)
    fi
fi

if [[ -z "${S3_ACCESSKEY:-}" || -z "${S3_SECRETKEY:-}" || -z "${S3_ENDPOINT:-}" || -z "${S3_REGION:-}" ]]; then
    >&2 echo "Define the 'S3_ACCESSKEY', 'S3_SECRETKEY', 'S3_ENDPOINT', 'S3_REGION' env variables or use a '$s3cfg' file."
    exit 1
fi

# Run jupyter lab on the 'sprints' directory. 
# Run Ctrl-C to exit.
jupyter lab "${ROOT_DIR}/sprints"

