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

# Change this if needed
DASK_GATEWAY_TAG="2024.1.0"

# Use the same requirements as for the dask-gateway-server docker image.
# Download them from https://github.com/dask/dask-gateway/blob/<tag>/dask-gateway-server/Dockerfile.requirements.txt
# into a local ./tmp folder.
cd "$SCRIPT_DIR"
tmp="./tmp"
rm -rf "$tmp" && mkdir -p "$tmp"
wget -P "$tmp" "https://raw.githubusercontent.com/dask/dask-gateway/refs/tags/${DASK_GATEWAY_TAG}/dask-gateway-server/Dockerfile.requirements.txt"

# But comment the line that installs dask-gateway-server from a Dockerfile.requirements.in file
req="${tmp}/Dockerfile.requirements.txt"
sed -i "s|\(^\s*dask-gateway-server\)|# \1|g" "$req"

# And instead do the same installation as in https://gateway.dask.org/install-local.html#installation
echo "dask-gateway==${DASK_GATEWAY_TAG}" >> "$req"
echo "dask-gateway-server[local]==${DASK_GATEWAY_TAG}" >> "$req"

# Build the docker image
registry="ghcr.io/rs-python/dask-gateway-server/local"
docker build \
    -f "Dockerfile.dask-gateway-server.local" \
    -t "${registry}:${DASK_GATEWAY_TAG}" \
    -t "${registry}:latest" \
    "$tmp"

# # Push the images
# docker login https://ghcr.io/v2/rs-python
# docker push "${registry}:${DASK_GATEWAY_TAG}"
# docker push "${registry}:latest"
