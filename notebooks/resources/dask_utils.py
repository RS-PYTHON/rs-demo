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

"""Utility Python module for the Jupyter demos, to be shared with the dask workers.

WARNING: AFTER EACH MODIFICATION, RESTART THE JUPYTER NOTEBOOK KERNEL !
"""

import asyncio
import os
import socket
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from dask_gateway import Gateway
from dask_gateway.auth import BasicAuth, JupyterHubAuth
from dask_gateway.client import GatewayCluster
from distributed.client import Client as DaskClient
from resources import utils
from rs_client.ogcapi.dpr_client import ClusterInfo

# In local mode, all your services are running locally.
# In cluster mode, we use the services deployed on the RS-Server website.
# This configuration is set in an environment variable.
local_mode: bool = os.getenv("RSPY_LOCAL_MODE") == "1"
cluster_mode: bool = not local_mode

# Dask gateways, clusters and clients
dask_cluster_staging_process: asyncio.subprocess.Process = None
dask_gateway_eopf: Gateway = None
dask_cluster_eopf: GatewayCluster = None
dask_client_eopf: DaskClient = None

# Information to connect to a DPR Dask cluster.
cluster_info_eopf: ClusterInfo = None


def get_ip_address() -> str:
    """Return IP address, see: https://stackoverflow.com/a/166520"""
    return socket.gethostbyname(socket.gethostname())


def get_dask_gateway(
    address: str,
) -> Gateway:
    """Return dask gateway"""

    if cluster_mode:
        try:
            # NOTE: JUPYTERHUB_API_TOKEN is the token that was used to setup the Dask clusters.
            # It is saved and read in the Prefect block "env-vars".
            # This is not the JUPYTERHUB_API_TOKEN that is initialized automatically at the Jupyter session startup.
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


def init_dask_cluster(
    address: str,
    public_domain: str,
    scale: int = 2,
    image: str = "",
    cluster_label: str = "",
    worker_cores: int = 1,
    worker_memory: float = 2.0,
    scheduler_memory_limit: int = 2,
    namespace="dask-gateway",
    **kwargs,
) -> tuple[Gateway, GatewayCluster, DaskClient]:
    """
    Return existing dask cluster or create one.

    Args:
        address: dask gateway url (internal to the cluster or docker network)
        public_domain: dask gateway public url domain
        scale: number of dask workers to create
        image: docker image name to use for the workers
        cluster_label: custom label to identify the cluster e.g. "dask-proc"
        worker_cores: number of worker cores
        worker_memory: worker memory in GB
        namespace: dask gateway namespace
        kwargs: additional keywoard arguments to pass to the method "gateway.new_cluster"
    """
    print(f"Connecting to dask gateway for {cluster_label!r}: {address} ...")
    gateway = get_dask_gateway(address)

    # Sort the clusters by newest first
    clusters = sorted(
        gateway.list_clusters(),
        key=lambda cluster: cluster.start_time,
        reverse=True,
    )
    for cluster in clusters:
        print(f"image = {cluster.name}")
    # Get existing dask cluster name, if any.
    existing = None
    if clusters:

        # In local mode, get the existing cluster with the expected cluster name.
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
        print(f"Get existing dask cluster: {existing!r}")
        cluster = gateway.connect(existing)

    # Else create one
    elif local_mode:
        print(f"Create new dask cluster")
        cluster = gateway.new_cluster(cluster_name=cluster_label)

    else:  # cluster_mode
        print(f"Create new dask cluster from docker image: {image!r}")
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
            **kwargs,
        )

    print(
        f"Dask dashboard for {cluster_label!r}: {cluster.dashboard_link.replace(address, public_domain)}",
    )

    # Scale the cluster and get the client
    gateway.scale_cluster(cluster.name, scale)
    client = cluster.get_client()

    # Wait for all workers to be up
    tries = 0
    while True:
        scaled = len(client.scheduler_info()["workers"])
        print(f"Dask workers for {cluster_label!r} are up: {scaled}/{scale}")
        if scaled >= scale:
            break
        tries += 1
        if tries >= float("inf"):  # deactivate timeout
            raise TimeoutError(
                f"Error waiting for all Dask workers for {cluster_label!r} to be up: {scaled}/{scale}",
            )
        time.sleep(5)
    return gateway, cluster, client


async def init_dask_cluster_staging(
    scale: int,
    image: str = (
        "ghcr.io/rs-python/dask/staging/local:latest"
        if local_mode
        else "ghcr.io/rs-python/dask/staging/k8s:latest"
    ),
    cluster_label: str = os.environ["RSPY_DASK_STAGING_CLUSTER_NAME"],
    timeout: int = 600,
):
    """Init existing staging dask cluster or create one.
    This calls the script `init_dask_cluster_staging.py` with a different Python environment, to have the correct version of Dask for the staging.
    Make sure the location of the environment used (first arg) is the same as the one defined in the Dockerfile.
    """
    global dask_cluster_staging_process

    # Timeout to make sure we don't get stuck in an infinite loop
    timout_time = time.time() + timeout

    # Call the subprocess with the correct environment
    dir_path = os.path.dirname(os.path.realpath(__file__))
    dask_cluster_staging_process = await asyncio.create_subprocess_exec(
        "/opt/venv/dask-staging/bin/python",
        f"{dir_path}/init_dask_cluster_staging.py",
        "--scale",
        str(scale),
        "--image",
        image,
        "--cluster-label",
        cluster_label,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    output = error = None
    full_error = ""
    # Wait for the message from the script signaling that the cluster is ready
    while not output or "Dask cluster initialized" not in output.decode():

        # Read an output line or pass if there is none yet
        try:
            output = await asyncio.wait_for(
                dask_cluster_staging_process.stdout.readline(),
                timeout=1,
            )
            print(output.decode(), end="")
        except TimeoutError:
            pass

        # Read an error line or pass if there is none yet
        try:
            error = await asyncio.wait_for(
                dask_cluster_staging_process.stderr.readline(),
                timeout=1,
            )
            full_error += error.decode()
        except TimeoutError:
            pass

        # If error contains "Error", raise an error. Sometimes only warnings are printed in stderr that's why we check the keyword "Error"
        if error and "Error" in error.decode():
            print("=== AN ERROR OCCURRED ===")
            print(full_error)
            dask_cluster_staging_process.kill()
            dask_cluster_staging_process = None
            raise RuntimeError(
                f"Error initializing staging dask cluster: {error.decode()}",
            )

        # Stop if we reach the timeout
        if time.time() > timout_time:
            print("=== TIMEOUT REACHED - ERROR OUTPUT ===")
            print(full_error)
            dask_cluster_staging_process.kill()
            dask_cluster_staging_process = None
            raise TimeoutError(
                f"Timeout: staging dask cluster did not initialize after {timeout} seconds.",
            )


def init_dask_cluster_eopf(
    local_mode_address: str,
    local_mode_address_public: str,
    scale: int,
    image: str,
    cluster_label: str,  # automatically suffixed so it will be e.g. "dask-proc.user.version"
    big_resources: bool = False,  # provide more ram and cpu
    *args,
    **kwargs,
):
    """
    Init existing eopf dask cluster or create one.

    NOTE: to find the maximum cluster resources that you can request per node, first init a dask cluster, then in k9s
    go to your allocated dask-worker -> push 'o' (Show Node) -> push 'd' (Describe) -> check 'Allocatable' values.
    Then decrease a little bit these values because the nodes also run other services.

    Several workers can fit into a single node depending on the resources you requested for each worker. Else new nodes
    will be allocated. To find the maximum of nodes you can request, in k9s, type
    ':nodepools' -> find your nodeAffinity -> check the 'MAX' column value.

    For big_resources=False and nodeAffinity=dask_worker_on_demand we have max: 3 CPU, 12GB RAM, 8 nodes.

    For big_resources=True and nodeAffinity=dask_scheduler we have max: 7 CPU, 58GB RAM, 1 node.

    """
    global dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf, cluster_info_eopf

    # Additional arguments to pass to the DPR cluster.
    # See: https://github.com/RS-PYTHON/rs-infra-core/blob/develop/docs/how-to/Dask-gateway.md
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
        "worker_memory": 12,  # In GB
        "scheduler_memory_limit": 60,  # In GB
        "worker_extra_pod_config": (
            scheduler_tuning if big_resources else worker_tuning
        ),
        "scheduler_extra_pod_config": scheduler_tuning,
    }

    # In local mode, the dask gateway address is different for each eopf cluster (l0, l1, ...)
    # We need this address in some config files. So we update this env var from the current cluster value.
    # NOTE: these variables will be overridden if we init several eopf clusters in the same demo.
    if local_mode:
        os.environ["DASK_GATEWAY_ADDRESS"] = os.environ[local_mode_address]
        os.environ["DASK_GATEWAY_PUBLIC"] = os.environ[local_mode_address_public]
        # Refresh Prefect blocks so flow workers read the gateway selected in the notebook.
        utils.init_prefect_blocks(_sync=True)

    # Add the owner id to the label
    final_label = cluster_label + f".{utils.OWNER_ID}"

    # Add the docker image version (after the ':', if any) to the label
    if len(splits := image.split(":")) > 1:
        final_label += f".{splits[-1]}"

    # Init the dask eopf cluster and update the global variables.
    # NOTE: here also these variables will be overridden if we init several eopf clusters in the same demo.
    dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf = init_dask_cluster(
        os.environ["DASK_GATEWAY_ADDRESS"],
        os.environ["DASK_GATEWAY_PUBLIC"],
        scale,
        image=image,
        cluster_label=final_label,
        *args,
        **(dpr_tuning | kwargs),  # set default DPR tuning
    )

    # Save the cluster info
    # NOTE: here also this variable will be overridden if we init several eopf clusters in the same demo.
    cluster_info_eopf = ClusterInfo(
        jupyter_token=os.environ["JUPYTERHUB_API_TOKEN"] if cluster_mode else "",
        cluster_label=final_label,
        cluster_instance=dask_cluster_eopf.name,
    )


def init_dask_cluster_mockup(
    *args,
    image=(
        "ghcr.io/rs-python/dask/mockup/local:latest"
        if local_mode
        else "ghcr.io/rs-python/dask/mockup/k8s:latest"
    ),
    cluster_label="dask-eopf-mockup",
    **kwargs,
):
    return init_dask_cluster_eopf(
        *args,
        local_mode_address="DASK_GATEWAY_EOPF_MOCKUP_ADDRESS",
        local_mode_address_public="DASK_GATEWAY_EOPF_MOCKUP_PUBLIC",
        image=image,
        cluster_label=cluster_label,
        **kwargs,
    )


def init_dask_cluster_cpm(
    *args,
    image=("ghcr.io/rs-python/dask/cpm2/k8s:latest"),
    cluster_label="dask-cpm",
    **kwargs,
):
    return init_dask_cluster_eopf(
        *args,
        local_mode_address=None,
        local_mode_address_public=None,
        image=image,
        cluster_label=cluster_label,
        **kwargs,
    )


def init_dask_cluster_l0(
    *args,
    image=(
        "ghcr.io/rs-python/dask/l0/local:latest"
        if local_mode
        else "ghcr.io/rs-python/dask/l0/k8s:latest"
    ),
    cluster_label="dask-l0",
    **kwargs,
):
    return init_dask_cluster_eopf(
        *args,
        local_mode_address="DASK_GATEWAY_L0_ADDRESS",
        local_mode_address_public="DASK_GATEWAY_L0_PUBLIC",
        image=image,
        cluster_label=cluster_label,
        **kwargs,
    )


def init_dask_cluster_s1ard(
    *args,
    image=(
        "ghcr.io/rs-python/dask/s1ard/local:latest"
        if local_mode
        else "ghcr.io/rs-python/dask/s1ard/k8s:latest"
    ),
    cluster_label="dask-s1ard",
    **kwargs,
):
    return init_dask_cluster_eopf(
        *args,
        local_mode_address="DASK_GATEWAY_S1ARD_ADDRESS",
        local_mode_address_public="DASK_GATEWAY_S1ARD_PUBLIC",
        image=image,
        cluster_label=cluster_label,
        **kwargs,
    )


def init_dask_cluster_s3olci(
    *args,
    image=(
        "ghcr.io/rs-python/dask/s3olci/local:latest"
        if local_mode
        else "ghcr.io/rs-python/dask/s3olci/k8s:latest"
    ),
    cluster_label="dask-s3olci",
    **kwargs,
):
    return init_dask_cluster_eopf(
        *args,
        local_mode_address="DASK_GATEWAY_S3OLCI_ADDRESS",
        local_mode_address_public="DASK_GATEWAY_S3OLCI_PUBLIC",
        image=image,
        cluster_label=cluster_label,
        **kwargs,
    )


def get_existing_cluster(
    address: str,
    name: str,
) -> tuple[Gateway, GatewayCluster, DaskClient]:
    """
    Return existing dask cluster from its gateway address and cluster name.
    Raise exceptions if the gateway or cluster do not already exist.
    Note: this is run from prefect worker so the print or logging won't show.
    """
    try:
        gateway = get_dask_gateway(address)
        cluster = gateway.connect(name)
        client = cluster.get_client()
        return gateway, cluster, client

    except Exception as exception:
        raise ConnectionError(
            f"Error connecting to dask gateway: {address!r} and cluster name: {name!r}",
        ) from exception


def close_dask_clusters():
    """Close dask gateway, cluster and client python objects."""
    global dask_client_eopf, dask_cluster_eopf, dask_gateway_eopf

    # First client, then cluster, then gateway
    for obj in (
        dask_client_eopf,
        dask_cluster_eopf,
        dask_gateway_eopf,
    ):
        if obj:
            obj.close()

    dask_client_eopf = None
    dask_cluster_eopf = None
    dask_gateway_eopf = None


def shutdown_dask_cluster_staging():
    """Shutdown the staging dask cluster by killing the subprocess."""
    global dask_cluster_staging_process

    if dask_cluster_staging_process:
        # Send STOP signal to subprocess to stop the staging cluster
        dask_cluster_staging_process.stdin.write(b"STOP\n")
        dask_cluster_staging_process.stdin.flush()
        dask_cluster_staging_process.wait()
        dask_cluster_staging_process = None


def shutdown_dask_clusters(gateway: Gateway, name: str | None):
    """
    Shutdown the given gateway cluster, or all clusters if the name is None.
    """
    for cluster_info in gateway.list_clusters():
        try:
            if (name is None) or (name == cluster_info.name):
                cluster = gateway.connect(cluster_info.name)
                cluster.shutdown()
                print(f"Shutting down cluster {cluster_info.name!r} ...")
        except Exception as e:
            print(f"Error shutting down cluster {cluster_info.name!r}: {e}")
