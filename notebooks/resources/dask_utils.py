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

"""Utility Python module for the tutorials, to be shared with the dask workers.

WARNING: AFTER EACH MODIFICATION, RESTART THE JUPYTER NOTEBOOK KERNEL !
"""

import os
import socket
import time

from dask_gateway import Gateway
from dask_gateway.auth import BasicAuth, JupyterHubAuth
from dask_gateway.client import GatewayCluster
from distributed.client import Client as DaskClient

# In local mode, all your services are running locally.
# In cluster mode, we use the services deployed on the RS-Server website.
# This configuration is set in an environment variable.
local_mode: bool = os.getenv("RSPY_LOCAL_MODE") == "1"
cluster_mode: bool = not local_mode

# Dask gateways, clusters and clients
dask_gateway_staging: Gateway = None
dask_cluster_staging: GatewayCluster = None
dask_client_staging: DaskClient = None
dask_gateway_eopf: Gateway = None
dask_cluster_eopf: GatewayCluster = None
dask_client_eopf: DaskClient = None


def get_ip_address() -> str:
    """Return IP address, see: https://stackoverflow.com/a/166520"""
    return socket.gethostbyname(socket.gethostname())


def get_dask_gateway(
    address: str,
) -> Gateway:
    """Return dask gateway"""

    if cluster_mode:
        try:
            auth = JupyterHubAuth(os.environ["JUPYTERHUB_API_TOKEN"])
        except KeyError as error:
            raise KeyError(
                "JUPYTERHUB_API_TOKEN environment variable is missing",
            ) from error

    else:  # local mode
        try:
            auth = BasicAuth(
                os.environ["LOCAL_DASK_USERNAME"],
                os.environ["LOCAL_DASK_PASSWORD"],
            )
        except KeyError as error:
            raise KeyError(
                "In local mode, call init_prefect_blocks() or blocks_to_env_vars() before this function.",
            ) from error

    return Gateway(address=address, auth=auth)


def init_dask_cluster(
    address: str,
    public_domain: str,
    scale: int = 2,
    image: str = "",
    cluster_tag: str = "",
    worker_cores: int = 1,
    worker_memory: float = 2.0,
    namespace="dask-gateway",
) -> tuple[Gateway, GatewayCluster, DaskClient]:
    """Return existing dask cluster or create one"""

    print(f"Connecting to dask gateway for {cluster_tag!r}: {address} ...")
    gateway = get_dask_gateway(address)

    # Sort the clusters by newest first
    clusters = sorted(
        gateway.list_clusters(),
        key=lambda cluster: cluster.start_time,
        reverse=True,
    )

    # Get existing dask cluster name, if any.
    existing = None
    if clusters:

        # In local mode, just get the first existing cluster.
        if local_mode:
            existing = clusters[0].name

        # In cluster mode, also check the docker image name
        else:
            existing = next(
                (
                    report.name
                    for report in clusters
                    if report.options.get("image") == image
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
        cluster = gateway.new_cluster()

    else:  # cluster_mode
        print(f"Create new dask cluster from docker image: {image!r}")
        cluster = gateway.new_cluster(
            worker_cores=worker_cores,
            worker_memory=worker_memory,
            namespace=namespace,
            image=image,
            cluster_name=cluster_tag,
            scheduler_extra_pod_labels={"cluster_name": cluster_tag},
        )

    print(
        f"Dask dashboard for {cluster_tag!r}: {cluster.dashboard_link.replace(address, public_domain)}",
    )

    # Scale the cluster and get the client
    gateway.scale_cluster(cluster.name, scale)
    client = cluster.get_client()

    # Wait for all workers to be up
    tries = 0
    while True:
        scaled = len(client.scheduler_info()["workers"])
        print(f"Dask workers for {cluster_tag!r} are up: {scaled}/{scale}")
        if scaled >= scale:
            break
        tries += 1
        if tries >= 60:
            raise TimeoutError(
                f"Error waiting for all Dask workers for {cluster_tag!r} to be up: {scaled}/{scale}",
            )
        time.sleep(5)

    # Forward logging from dask workers to the caller.
    # NOTE: we need to use the logging in the workers, "print" won't be forwarded.
    client.forward_logging()

    return gateway, cluster, client


def init_dask_cluster_staging(
    scale: int,
    image: str = "ghcr.io/rs-python/rs-infrastructure-dask-staging:latest",
    *args,
    **kwargs,
):
    """Init existing staging dask cluster or create one"""
    global dask_gateway_staging, dask_cluster_staging, dask_client_staging
    dask_gateway_staging, dask_cluster_staging, dask_client_staging = init_dask_cluster(
        (
            os.environ["DASK_GATEWAY_ADDRESS"]
            if cluster_mode
            else os.environ["DASK_GATEWAY_STAGING_ADDRESS"]
        ),
        (
            os.environ["DASK_GATEWAY_PUBLIC"]
            if cluster_mode
            else os.environ["DASK_GATEWAY_STAGING_PUBLIC"]
        ),
        scale,
        image=image,
        cluster_tag="dask-staging",
        *args,
        **kwargs,
    )


def init_dask_cluster_eopf(
    scale: int,
    image: str = "ghcr.io/rs-python/rs-infrastructure-dask-eopf:latest",
    *args,
    **kwargs,
):
    """Init existing eopf dask cluster or create one"""
    global dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf
    dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf = init_dask_cluster(
        (
            os.environ["DASK_GATEWAY_ADDRESS"]
            if cluster_mode
            else os.environ["DASK_GATEWAY_EOPF_ADDRESS"]
        ),
        (
            os.environ["DASK_GATEWAY_PUBLIC"]
            if cluster_mode
            else os.environ["DASK_GATEWAY_EOPF_PUBLIC"]
        ),
        scale,
        image=image,
        cluster_tag="dask-eopf",
        *args,
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

        # Forward logging from dask workers to the caller.
        # NOTE: we need to use the logging in the workers, "print" won't be forwarded.
        client.forward_logging()

        return gateway, cluster, client

    except Exception as exception:
        raise ConnectionError(
            f"Error connecting to dask gateway: {address!r} and cluster name: {name!r}",
        ) from exception


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
