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

# Examples for usage (outside the rs-demo dir)
# -> GITLAB_EOPF_TOKEN=<token> rs-demo/local-mode/docker/build.dask-eopf-local.sh mockup feat-rspyNNN --push
# This will build and push the image with the dpr mockup, with tag feat-rspyNNN
# -> GITLAB_EOPF_TOKEN=<token> rs-demo/local-mode/docker/build.dask-eopf-local.sh local feat-rspyMMM --push
# This will build and push the image with the real dpr processor, with tag feat-rspyMMM
# -> GITLAB_EOPF_TOKEN=<token> rs-demo/local-mode/docker/build.dask-eopf-local.sh all latest --push
# This will build and push the images with the dpr mockup and real dpr processor, both with tag latest

set -euo pipefail
set -x

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

DASK_GATEWAY_TAG=2024.1.0
PREFECT_TAG=3.2.13
PREFECT_DASK_TAG=0.3.3

# Determine what to build
# Options: local, mockup, all
BUILD_TARGET="${1:-all}"
shift || true

# Options: <your-tag>, latest (default)
TAG_TO_USE="${1:-latest}"
shift || true

set +x
if [[ -z "${GITLAB_EOPF_TOKEN:-}" ]]; then
    >&2 echo -e "usage: GITLAB_EOPF_TOKEN=*** $0\n(see: https://gitlab.eopf.copernicus.eu/help/user/profile/personal_access_tokens)"
    exit 1
fi
set -x

# Function to build and optionally push a docker image
build_and_push() {
    local image_name=$1
    local dockerfile=$2
    local registry=$3
    # shift off the first three fixed arguments
    shift 3

    docker build \
        --build-arg "DASK_GATEWAY_TAG=${DASK_GATEWAY_TAG}" \
        --build-arg "PREFECT_TAG=${PREFECT_TAG}" \
        --build-arg "PREFECT_DASK_TAG=${PREFECT_DASK_TAG}" \
        --secret id=GITLAB_EOPF_TOKEN \
        -f "${SCRIPT_DIR}/${dockerfile}" \
        -t "${registry}:${TAG_TO_USE}" \
        --progress=plain \
        "$SCRIPT_DIR"

    if [[ " $@ " == *" --push "* ]]; then
        docker login https://ghcr.io/v2/rs-python
        docker push "${registry}:${TAG_TO_USE}"
    fi
}

# Build according to the selected target
# first image: the one that contains the real dpr processor
if [[ "$BUILD_TARGET" == "local" || "$BUILD_TARGET" == "all" ]]; then
    build_and_push "local" "l0/Dockerfile.dask-l0-local" "ghcr.io/rs-python/dask-gateway-server/l0/local" "$@"
    build_and_push "local" "s1ard/Dockerfile.dask-s1ard-local" "ghcr.io/rs-python/dask-gateway-server/s1ard/local" "$@"
fi
# second image: the one that contains the dpr processor mockup
if [[ "$BUILD_TARGET" == "mockup" || "$BUILD_TARGET" == "all" ]]; then
    build_and_push "mockup" "Dockerfile.dask-eopf-mockup-local" "ghcr.io/rs-python/dask-gateway-server/eopf/mockup-local" "$@"
fi
# rs-dpr-service + real dpr processor in same image
if [[ "$BUILD_TARGET" == "localcluster" || "$BUILD_TARGET" == "all" ]]; then
    docker pull "ghcr.io/rs-python/rs-dpr-service:latest"
    build_and_push "localcluster" "l0/Dockerfile.dask-eopf-localcluster" "ghcr.io/rs-python/dask-gateway-server/l0/localcluster" "$@"
fi
