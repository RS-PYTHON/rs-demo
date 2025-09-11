#!/usr/bin/env python3

# Copyright 2025 CS Group
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

"""Build the dask eopf images for local mode."""

import argparse
import itertools
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# NOTE: run "./build.dask-eopf-local.py -h" to display help.

DASK_GATEWAY_TAG = "2024.1.0"
PREFECT_TAG = "3.2.13"
PREFECT_DASK_TAG = "0.3.3"

# This script directory
THIS_DIR = Path(__file__).parent

########
# Init #
########


@dataclass
class Image:
    """Docker image information"""

    # Docker image name (registry)
    name: str

    # Name of the LocalCluster image (for debugging)
    local_cluster_name: str = ""

    # Used to identify the image to build
    image2build: str = ""


# All possible processor images
all_procs = {
    "mockup": Image("ghcr.io/rs-python/dask-gateway-server/eopf/mockup-local"),
    "l0": Image(
        "ghcr.io/rs-python/dask-gateway-server/l0/local",
        "ghcr.io/rs-python/dask-gateway-server/l0/localcluster",
        "dask-l0",
    ),
    "s1ard": Image(
        "ghcr.io/rs-python/dask-gateway-server/s1ard/local",
        "ghcr.io/rs-python/dask-gateway-server/s1ard/localcluster",
        "dask-s1ard",
    ),
}

######################
# PARSE COMMAND LINE #
######################

parser = argparse.ArgumentParser(
    description="Build the dask eopf images for local mode",
    epilog=f"Example: {sys.argv[0]} l0 -t=*** -d=feat-rspyxxx --push",
)

# Positional argument
parser.add_argument(
    "proc",
    choices=["all"] + list(all_procs.keys()),
    help="Processor to build",
)

# Named arguments
parser.add_argument(
    "-t",
    "--gitlab_eopf_token",
    required=True,
    help="See: 'https://gitlab.eopf.copernicus.eu/help/user/profile/personal_access_tokens'",
)
parser.add_argument(
    "-l",
    "--local_cluster",
    action="store_true",
    help="Build the Dask LocalCluster image for local debugging",
)
parser.add_argument("-d", "--docker_tag", default="latest", help="Docker tag to use")
parser.add_argument(
    "-p",
    "--push",
    action="store_true",
    help="Push image to Docker registry",
)

args = parser.parse_args()

######################
# BUILD DOCKER IMAGE #
######################

# Build all images ?
build_all = args.proc == "all"

# Nominal case: we build a single processor with or without local cluster
if not build_all:
    procs_to_build = [[args.proc, args.local_cluster]]

# Build all the processors, with and without local cluster
else:
    procs_to_build = list(itertools.product(all_procs.keys(), [False, True]))

for proc, local_cluster in procs_to_build:

    # Handle special cases
    if (proc == "mockup") and local_cluster:
        if build_all:
            continue
        raise RuntimeError("No LocalCluster image for mockup")

    def get_dockerfile() -> Path:
        """Return Dockerfile to use"""
        if proc == "mockup":
            return THIS_DIR / "Dockerfile.dask-eopf-mockup-local"
        if local_cluster:
            return THIS_DIR / "Dockerfile.dask-eopf-localcluster"
        # default
        return THIS_DIR / "Dockerfile.dask-eopf-local"

    def run_command(command: list[str]):
        """Run command line"""
        if code := subprocess.run(
            command,
            env={"GITLAB_EOPF_TOKEN": args.gitlab_eopf_token},
        ).returncode:
            joined = "' '"
            raise RuntimeError(
                f"Error running command:\n'{joined.join(command)}'\nReturn code: {code}",
            )

    # Docker image information
    image = all_procs[proc]

    # Docker image name
    registry = image.local_cluster_name if local_cluster else image.name

    # Build image
    run_command(
        [
            "docker",
            "build",
            "--build-arg",
            f"IMAGE2BUILD={image.image2build}",
            "--build-arg",
            f"DASK_GATEWAY_TAG={DASK_GATEWAY_TAG}",
            "--build-arg",
            f"PREFECT_TAG={PREFECT_TAG}",
            "--build-arg",
            f"PREFECT_DASK_TAG={PREFECT_DASK_TAG}",
            "--secret",
            f"id=GITLAB_EOPF_TOKEN",
            "-f",
            str(get_dockerfile()),
            "-t",
            f"{registry}:{args.docker_tag}",
            "--progress=plain",
            str(THIS_DIR),
        ],
    )

    # Push to registry
    if args.push:
        run_command(
            [
                "/bin/sh",
                "-c",
                f"docker login https://ghcr.io/v2/rs-python && docker push '{registry}:{args.docker_tag}'",
            ],
        )
