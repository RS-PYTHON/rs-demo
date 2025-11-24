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

# This script builds the base dask docker images that are used for the local and cluster modes

set -euo pipefail
set -x

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# We use a different python version in eopf + the dpr processors + rs-dpr-service
PYTHON_VERSION=3.13.9
PYTHON_VERSION_DPR=3.11.7

DASK_GATEWAY_TAG=2024.1.0
DASK_TAG=2024.5.2

for python_version in $PYTHON_VERSION $PYTHON_VERSION_DPR; do

    # Checkout the dask-gateway git repository into a local ./tmp folder
    cd "$SCRIPT_DIR"
    tmp="./tmp/py${python_version}"
    mkdir -p "$tmp"
    tmp=$(realpath $tmp)
    cd "$tmp"
    git clone git@github.com:dask/dask-gateway.git || true # don't fail if already cloned
    cd dask-gateway
    git checkout "tags/$DASK_GATEWAY_TAG"
    git reset --hard

    # Change the base python version to use from the Dockerfile
    # FROM python:<version>-<something...> -> FROM python:<new_version>-<something...>
    dockerfile=$(realpath "dask-gateway/Dockerfile")
    sed -i "s|FROM python:[^-]*|FROM python:${python_version}|g" "$dockerfile"

    # For newer python versions, replace bullseye by bookworm
    python_tag="bullseye"
    if [[ "${python_version}" > "3.13.6" ]]; then
        sed -i "s|bullseye|bookworm|g" "$dockerfile"
        python_tag="bookworm"
    fi

    # Refreeze Dockerfile.requirements.txt based on Dockerfile.requirements.in
    # as in https://github.com/dask/dask-gateway/blob/2024.1.0/.github/workflows/refreeze-dockerfile-requirements-txt.yaml#L34
    matrix_image="dask-gateway"
    (\
        cd "${matrix_image}" && \
        echo docker run --rm \
            --volume=$PWD:/opt/${matrix_image} \
            --workdir=/opt/${matrix_image} \
            --user=root \
            "python:${python_version}-slim-${python_tag}" \
            sh -c 'pip install pip-tools==6.* && pip-compile --upgrade --output-file=Dockerfile.requirements.txt Dockerfile.requirements.in' \
    )
    req=$(realpath "${matrix_image}/Dockerfile.requirements.txt")

    # Force the dask versions
    sed -i "s|dask==.*|dask==${DASK_TAG}|g" "$req"
    sed -i "s|distributed==.*|distributed==${DASK_TAG}|g" "$req"
    sed -i "s|fsspec==.*|fsspec|g" "$req"

    # Build this first intermediate docker image
    target="ghcr.io/rs-python/dask/dask-gateway:${DASK_GATEWAY_TAG}-py${python_version}"
    base_target="${target}-base"
    echo docker build \
        -f "$dockerfile" \
        -t "$base_target" \
        --progress=plain \
        $(dirname "$dockerfile")

    # Then add our custom Dockerfile
    docker build \
        --build-arg "BASE=${base_target}" \
        -f "${SCRIPT_DIR}/Dockerfile.dask-base" \
        -t "${target}" \
        --progress=plain \
        "${SCRIPT_DIR}"

    # Push the docker iamge to the registry, if the --push option is specified.
    if [[ " $@ " == *" --push "* ]]; then
        docker login https://ghcr.io/v2/rs-python
        docker push "${target}"
    fi
done
