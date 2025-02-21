#!/usr/bin/env bash
# Copyright 2024 CS Group
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

set -euo pipefail
set -x

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

DASK_GATEWAY_TAG="2024.1.0"
PREFECT_TAG="3.1.4"

set +x
if [[ -z "${GITLAB_EOPF_TOKEN:-}" ]]; then
    >&2 echo -e "usage: GITLAB_EOPF_TOKEN=*** $0\n(see: https://gitlab.eopf.copernicus.eu/help/user/profile/personal_access_tokens)"
    exit 1
fi
set -x

# Build the docker image
registry="ghcr.io/rs-python/dask-gateway-server/eopf/local"
docker build \
    --build-arg "DASK_GATEWAY_TAG=${DASK_GATEWAY_TAG}" \
    --build-arg "PREFECT_TAG=${PREFECT_TAG}" \
    --secret id=GITLAB_EOPF_TOKEN \
    -f "${SCRIPT_DIR}/Dockerfile.dask-eopf-local" \
    -t "${registry}:latest" \
    --progress=plain \
    "$SCRIPT_DIR" \

# Push the images
docker login https://ghcr.io/v2/rs-python
docker push "${registry}:latest"
