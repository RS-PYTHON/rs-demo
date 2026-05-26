#!/opt/conda/envs/py3.11.7-2026.1.2/bin/python
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

"""Script to initialize a dask-cpm cluster from the CPM Dask environment."""

import argparse
import os
import sys
import time

import dask
from dask_gateway import Gateway
from dask_gateway.auth import BasicAuth, JupyterHubAuth

local_mode: bool = os.getenv("RSPY_LOCAL_MODE") == "1"
cluster_mode: bool = not local_mode


def printflush(message: str):
    """Print and flush immediately so the parent notebook sees progress."""
    print(message)
    sys.stdout.flush()


def get_dask_gateway(address: str) -> Gateway:
    """Return dask gateway."""
    if cluster_mode:
        try:
            auth = JupyterHubAuth(os.environ["JUPYTERHUB_API_TOKEN"])
        except KeyError as error:
            raise KeyError(
                "JUPYTERHUB_API_TOKEN environment variable is missing",
            ) from error
    else:
        auth = BasicAuth(
            os.environ["LOCAL_DASK_USERNAME"],
            os.environ["LOCAL_DASK_PASSWORD"],
        )

    return Gateway(address=address, auth=auth)


def init_dask_cluster_cpm(
    scale: int,
    image: str,
    cluster_label: str,
):
    """Init existing CPM dask cluster or create one."""
    worker_tuning = {
        "affinity": {
            "nodeAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "node-role.kubernetes.io/dask_worker_on_demand",
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
                "value": "dask_worker_on_demand",
                "effect": "NoSchedule",
            },
        ],
    }
    scheduler_tuning = {
        "affinity": {
            "nodeAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "node-role.kubernetes.io/dask_scheduler",
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
                "value": "dask_scheduler",
                "effect": "NoSchedule",
            },
        ],
    }
    dpr_tuning = {
        "worker_cores": 3,
        "worker_memory": 12,
        "scheduler_memory_limit": 60,
        "worker_extra_pod_config": worker_tuning,
        "scheduler_extra_pod_config": scheduler_tuning,
    }

    address = (
        os.environ["DASK_GATEWAY_ADDRESS"]
        if cluster_mode
        else os.environ["DASK_GATEWAY_CPM2_ADDRESS"]
    )
    public_domain = (
        os.environ["DASK_GATEWAY_PUBLIC"]
        if cluster_mode
        else os.environ["DASK_GATEWAY_CPM2_PUBLIC"]
    )

    printflush(f"Connecting to dask gateway for {cluster_label!r}: {address} ...")
    gateway = get_dask_gateway(address)

    clusters = sorted(
        gateway.list_clusters(),
        key=lambda cluster: cluster.start_time,
        reverse=True,
    )

    existing = None
    if clusters:
        if local_mode:
            existing = next(
                (
                    report.name
                    for report in clusters
                    if isinstance(report.options, dict)
                    and report.options.get("cluster_name") == cluster_label
                ),
                None,
            )
        else:
            existing = next(
                (
                    report.name
                    for report in clusters
                    if report.options.get("image") == image
                    and report.options.get("cluster_name") == cluster_label
                ),
                None,
            )

    if existing:
        printflush(f"Get existing dask cluster: {existing!r}")
        cluster = gateway.connect(existing)
    elif local_mode:
        printflush("Create new dask cluster")
        cluster = gateway.new_cluster(cluster_name=cluster_label)
    else:
        printflush(f"Create new dask cluster from docker image: {image!r}")
        worker_cores = dpr_tuning["worker_cores"]
        worker_memory = dpr_tuning["worker_memory"]
        cluster = gateway.new_cluster(
            worker_cores=worker_cores,
            worker_memory=worker_memory,
            cluster_max_workers=scale + 1,
            cluster_max_cores=(scale + 1) * worker_cores,
            cluster_max_memory=(scale + 1) * worker_memory * (2**30),
            scheduler_memory_limit=dpr_tuning["scheduler_memory_limit"],
            namespace="dask-gateway",
            image=image,
            cluster_name=cluster_label,
            scheduler_extra_pod_labels={"cluster_name": cluster_label},
            worker_extra_pod_config=dpr_tuning["worker_extra_pod_config"],
            scheduler_extra_pod_config=dpr_tuning["scheduler_extra_pod_config"],
        )

    printflush(f"Dask cluster name: {cluster.name}")
    printflush(
        f"Dask dashboard for {cluster_label!r}: {cluster.dashboard_link.replace(address, public_domain)}",
    )

    gateway.scale_cluster(cluster.name, scale)
    client = cluster.get_client()

    tries = 0
    while True:
        scaled = len(client.scheduler_info()["workers"])
        printflush(f"Dask workers for {cluster_label!r} are up: {scaled}/{scale}")
        if scaled >= scale:
            break
        tries += 1
        if tries >= float("inf"):
            raise TimeoutError(
                f"Error waiting for all Dask workers for {cluster_label!r} to be up: {scaled}/{scale}",
            )
        time.sleep(5)

    return cluster.name


def main():
    """Initialize the CPM dask cluster and keep it alive until STOP."""
    parser = argparse.ArgumentParser(description="Initialize dask-cpm cluster")
    parser.add_argument(
        "--scale",
        type=int,
        default=1,
        help="Number of dask workers to create",
    )
    parser.add_argument(
        "--image",
        type=str,
        default="ghcr.io/rs-python/dask/cpm2/k8s:latest",
        help="Docker image name to use for the workers",
    )
    parser.add_argument(
        "--cluster-label",
        type=str,
        default="dask-cpm",
        help="Custom cluster label",
    )
    args = parser.parse_args()

    printflush("Initializing dask-cpm cluster. This can take some time...")
    printflush(f"Dask version used: {dask.__version__}")

    init_dask_cluster_cpm(
        scale=args.scale,
        image=args.image,
        cluster_label=args.cluster_label,
    )

    printflush("Dask cluster initialized. Waiting for STOP signal to exit...")

    for line in sys.stdin:
        if line.strip() == "STOP":
            printflush("STOP signal received. Exiting...")
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
