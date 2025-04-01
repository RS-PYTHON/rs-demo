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

PYTHON_VERSION=3.13.2
DASK_GATEWAY_TAG=2024.1.0

# Checkout the dask-gateway git repository into a local ./tmp folder
cd "$SCRIPT_DIR"
tmp="./tmp"
mkdir -p "$tmp"
cd "$tmp"
git clone git@github.com:dask/dask-gateway.git || true # don't fail if already cloned
cd dask-gateway
git checkout "tags/$DASK_GATEWAY_TAG"

# Change the base python version to use from the Dockerfile
# FROM python:<version>-<something...> -> FROM python:<new_version>-<something...>
dockerfile=$(realpath "dask-gateway/Dockerfile")
sed -i "s|FROM python:[^-]*|FROM python:${PYTHON_VERSION}|g" "$dockerfile"

# Refreeze Dockerfile.requirements.txt based on Dockerfile.requirements.in
# as in https://github.com/dask/dask-gateway/blob/main/.github/workflows/refreeze-dockerfile-requirements-txt.yaml#L34
matrix_image="dask-gateway-server"
(\
    cd "${matrix_image}" && \
    docker run --rm \
        --volume=$PWD:/opt/${matrix_image} \
        --workdir=/opt/${matrix_image} \
        --user=root \
        "python:${PYTHON_VERSION}-slim-bullseye" \
        sh -c 'pip install pip-tools==6.* && pip-compile --upgrade --output-file=Dockerfile.requirements.txt Dockerfile.requirements.in' \
)
req=$(realpath "${matrix_image}/Dockerfile.requirements.txt")

# Comment the line that installs dask-gateway-server from a Dockerfile.requirements.in file.
# We install it in our Dockerfile instead.
sed -i "s|\(^\s*dask-gateway-server\)|# \1|g" "$req"

# Build the docker image
registry="ghcr.io/rs-python/dask-gateway-server/base/local"
context=$(realpath "./dask-gateway-server")
cp "${SCRIPT_DIR}/layer-cleanup.sh" "$context"
docker build \
    -f "${SCRIPT_DIR}/Dockerfile.dask-base-local" \
    -t "${registry}:${DASK_GATEWAY_TAG}" \
    --progress=plain \
    "$context"

# Push the docker iamge to the registry, if the --push option is specified.
if [[ " $@ " == *" --push "* ]]; then
    docker login https://ghcr.io/v2/rs-python
    docker push "${registry}:${DASK_GATEWAY_TAG}"
fi
