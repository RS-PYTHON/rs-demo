#!/usr/bin/env bash

set -eo pipefail # don't use -u
#set -x

# Read RSPY environment variables
source /tmp/.env

# Give all permissions to the docker named volumes "rspy_working_dir".
# This is for the docker containers that will be run as non-root.
chmod 777 ${RSPY_WORKING_DIR}

# The .env file defines the config file paths as they should be installed
# inside the Docker container.
for target_config in ${EODAG_ADGS_CONFIG} ${EODAG_CADIP_CONFIG} ${RSPY_STATION_CONFIG}; do

    # The source config file is in ./config with the same filename
    source_config=/tmp/config/$(basename ${target_config})

    # Create target directory and copy file
    mkdir -p $(dirname ${target_config})
    cp -f ${source_config} ${target_config}
    
done