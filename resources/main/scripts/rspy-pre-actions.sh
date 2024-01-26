#!/usr/bin/env bash

set -euo pipefail

# Read RSPY environment variables
source /docker/compose/dir/.env

# Give all permissions to the docker named volumes "rspy_working_dir".
# This is for the docker containers that will be run as non-root.
(set -x; chmod 777 ${RSPY_WORKING_DIR})

# The .env file defines the config file paths as they should be installed
# inside the Docker container.
for target_config in ${EODAG_ADGS_CONFIG} ${EODAG_CADIP_CONFIG} ${RSPY_STATION_CONFIG}; do

    # The source config file is in ./config with the same filename
    source_config=/docker/compose/dir/main/config/$(basename ${target_config})

    # Create target directory and copy file
    mkdir -p $(dirname ${target_config})
    (set -x; cp -f ${source_config} ${target_config})
    
done

# Wait for the stac service to be up. 
# It is defined in rs-demo/resources/stac/stac-fastapi-pgstac/docker-compose.yml
/docker/compose/dir/stac/stac-fastapi-pgstac/scripts/wait-for-it.sh stac-fastapi-pgstac:8082