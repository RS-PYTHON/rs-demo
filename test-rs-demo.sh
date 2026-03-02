#!/usr/bin/env bash
# Copyright 2026 Airbus, CS Group
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


# Standalone script to run rs-demo tests
# - runs notebooks
# - on failure: dumps last 100 lines of logs for each container
# - always cleans up docker compose

set -euo pipefail
set -x

#############################
# Configuration
#############################

COMPOSE_FILE="docker-compose-test-tag.yml"
LOG_LINES=200

#############################
# S3 configuration
#############################

# Copy the s3cmd config file to be able to access the "real" s3 bucket
echo "${S3CFG_OVH_BUCKET:-}" > ~/.s3cfg

#############################
# Checkout branch
#############################

# Try to checkout in rs-demo the same branch name than in rs-server.
# If the branch doesn't exist, it's ok, we stay on the default branch.
git checkout "${BRANCH_NAME:-}" || true
git status

#############################
# Start local mode
#############################

cd local-mode
DOCKER_TAG="${DOCKER_TAG:-latest}"
./test-docker-tag.sh "${DOCKER_TAG}"
docker compose -f "${COMPOSE_FILE}" up cicd -d

#############################
# Run notebooks & get status
#############################

set +e
./run-notebooks.sh
NOTEBOOKS_STATUS=$?
set -e

#############################
# Handle failure
#############################

if [[ ${NOTEBOOKS_STATUS} -ne 0 ]]; then
  echo ""
  echo "#############################################"
  echo "# ❌ One or more notebooks failed"
  echo "# 📋 Dumping container logs (last ${LOG_LINES} lines)"
  echo "#############################################"

  SERVICES=$(docker compose -f "${COMPOSE_FILE}" ps --services)

  for svc in ${SERVICES}; do
    echo ""
    echo "============================================================"
    echo "🧩 Service: ${svc}"
    echo "============================================================"
    docker compose -f "${COMPOSE_FILE}" logs --tail="${LOG_LINES}" "${svc}"
  done

  echo ""
  echo "#############################################"
  echo "# 🧹 Shutting down docker compose"
  echo "#############################################"

  docker compose -f "${COMPOSE_FILE}" down -v

  exit "${NOTEBOOKS_STATUS}"
fi

#############################
# Success path
#############################

docker compose -f "${COMPOSE_FILE}" down -v

echo ""
echo "#############################################"
echo "# ✅ All notebooks executed successfully"
echo "#############################################"
