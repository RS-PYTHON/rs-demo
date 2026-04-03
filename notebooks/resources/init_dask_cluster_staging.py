#!/home/jovyan/dask-staging/bin/python
# Copyright 2023-2026 Airbus, CS Group
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

"""Script to initialize a dask cluster for staging.
Most of the code is copy-pasted from the "dask_utils.py" file, but the dask images for
the staging use a different dask version than the processors so we need a separate virtual
environment for these functions.
"""

import argparse
import os
import sys
import time

import dask
from dask_gateway import Gateway
from dask_gateway.auth import BasicAuth, JupyterHubAuth

# In local mode, all your services are running locally.
# In cluster mode, we use the services deployed on the RS-Server website.
# This configuration is set in an environment variable.
local_mode: bool = os.getenv("RSPY_LOCAL_MODE") == "1"
cluster_mode: bool = not local_mode


def printflush(message: str):
    """Utility function to print messages and flush the output immediately."""
    print(message)
    sys.stdout.flush()


def get_dask_gateway(
    address: str,
) -> Gateway:
    """Return dask gateway.
    Copy-pasted from "dask_utils.py"."""

    if cluster_mode:
        try:
            auth = JupyterHubAuth(os.environ["JUPYTERHUB_API_TOKEN"])
        except KeyError as error:
            raise KeyError(
                "JUPYTERHUB_API_TOKEN environment variable is missing",
            ) from error

    else:  # local mode
        auth = BasicAuth(
            os.environ["LOCAL_DASK_USERNAME"],
            os.environ["LOCAL_DASK_PASSWORD"],
        )

    return Gateway(address=address, auth=auth)


def init_dask_cluster_staging(
    scale: int,
    image: str = "ghcr.io/rs-python/dask/staging/k8s:latest",
    cluster_label: str = os.environ["RSPY_DASK_STAGING_CLUSTER_NAME"],
):
    """Init existing staging dask cluster or create one.
    Mostly copy-pasted from "dask_utils.py", with adjustments for the staging cluster configuration.
    """

    # Additional arguments to pass to the DPR cluster.
    # See: https://github.com/RS-PYTHON/rs-infra-core/blob/develop/docs/how-to/Dask-gateway.md
    dpr_tuning = {
        "worker_extra_pod_config": {
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "node-role.kubernetes.io/access_csc",
                                        "operator": "Exists",
                                    },
                                ],
                            },
                        ],
                    },
                },
            },
            "tolerations": [
                {
                    "key": "role",
                    "operator": "Equal",
                    "value": "access_csc",
                    "effect": "NoSchedule",
                },
            ],
        },
        "scheduler_extra_pod_config": {
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "node-role.kubernetes.io/access_csc",
                                        "operator": "Exists",
                                    },
                                ],
                            },
                        ],
                    },
                },
            },
            "tolerations": [
                {
                    "key": "role",
                    "operator": "Equal",
                    "value": "access_csc",
                    "effect": "NoSchedule",
                },
            ],
        },
    }

    address = (
        os.environ["DASK_GATEWAY_ADDRESS"]
        if cluster_mode
        else os.environ["DASK_GATEWAY_STAGING_ADDRESS"]
    )
    public_domain = (
        os.environ["DASK_GATEWAY_PUBLIC"]
        if cluster_mode
        else os.environ["DASK_GATEWAY_STAGING_PUBLIC"]
    )

    printflush(f"Connecting to dask gateway for {cluster_label!r}: {address} ...")
    gateway = get_dask_gateway(address)

    # Sort the clusters by newest first
    clusters = sorted(
        gateway.list_clusters(),
        key=lambda cluster: cluster.start_time,
        reverse=True,
    )
    for cluster in clusters:
        printflush(f"image = {cluster.name}")
    # Get existing dask cluster name, if any.
    existing = None
    if clusters:

        # In local mode, get the existing cluster with the expected cluster name.
        if local_mode:
            existing = next(
                (
                    report.name
                    for report in clusters
                    if report.options.get("cluster_name") == cluster_label
                ),
                None,
            )

        # In cluster mode, also check the docker image name and cluster name
        else:
            existing = next(
                (
                    report.name
                    for report in clusters
                    if (report.options.get("image") == image)
                    and (report.options.get("cluster_name") == cluster_label)
                ),
                None,
            )

    # If a cluster has already been initialized, retrieve it
    if existing:
        printflush(f"Get existing dask cluster: {existing!r}")
        cluster = gateway.connect(existing)

    # Else create one
    elif local_mode:
        printflush(f"Create new dask cluster")
        cluster = gateway.new_cluster(cluster_name=cluster_label)

    else:  # cluster_mode
        printflush(f"Create new dask cluster from docker image: {image!r}")
        worker_cores = 1
        worker_memory = 2.0
        scheduler_memory_limit = 2
        namespace = "dask-gateway"
        cluster = gateway.new_cluster(
            worker_cores=worker_cores,
            worker_memory=worker_memory,
            cluster_max_workers=scale + 1,
            cluster_max_cores=(scale + 1) * worker_cores,
            cluster_max_memory=(scale + 1) * worker_memory * (2**30),  # from GB to B
            scheduler_memory_limit=scheduler_memory_limit,
            namespace=namespace,
            image=image,
            cluster_name=cluster_label,
            scheduler_extra_pod_labels={"cluster_name": cluster_label},
            **(dpr_tuning),
        )

    printflush(
        f"Dask dashboard for {cluster_label!r}: {cluster.dashboard_link.replace(address, public_domain)}",
    )

    # Scale the cluster and get the client
    gateway.scale_cluster(cluster.name, scale)
    client = cluster.get_client()

    # Wait for all workers to be up
    tries = 0
    while True:
        scaled = len(client.scheduler_info()["workers"])
        printflush(f"Dask workers for {cluster_label!r} are up: {scaled}/{scale}")
        if scaled >= scale:
            break
        tries += 1
        if tries >= float("inf"):  # deactivate timeout
            raise TimeoutError(
                f"Error waiting for all Dask workers for {cluster_label!r} to be up: {scaled}/{scale}",
            )
        time.sleep(5)
    return gateway, cluster, client


def main():
    """Function to control the script execution through commmand line arguments.
    When launched, the script will initialize the dask cluster and keep it alive until it receives a "STOP" signal through the stdin.
    """
    # Get arguments from input
    parser = argparse.ArgumentParser(description="Initialize dask cluster for staging")
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="Number of dask workers to create",
    )
    parser.add_argument(
        "--image",
        type=str,
        default="ghcr.io/rs-python/dask/staging/k8s:latest",
        help="Docker image name to use for the workers",
    )
    parser.add_argument(
        "--cluster-label",
        type=str,
        default=os.environ["RSPY_DASK_STAGING_CLUSTER_NAME"],
        help="Custom label to identify the cluster e.g. 'dask-proc'",
    )
    args = parser.parse_args()

    printflush("Initializing dask cluster for staging. This can take some time...")
    printflush(f"Dask version used: {dask.__version__}")

    # Start staging cluster
    init_dask_cluster_staging(
        scale=args.scale,
        image=args.image,
        cluster_label=args.cluster_label,
    )

    # Send message that cluster is ready
    printflush("Dask cluster initialized. Waiting for STOP signal to exit...")

    # Keep the script alive to keep the cluster up until "STOP" is sent to the stdin.
    for line in sys.stdin:
        if line.strip() == "STOP":
            printflush("STOP signal received. Exiting...")
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
