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

from dask_gateway import Gateway
from dask_gateway.auth import BasicAuth, JupyterHubAuth
from dask_gateway.client import GatewayCluster
from distributed.client import Client as DaskClient
from prefect.blocks.system import JSON as JsonBlock
from prefect.blocks.system import Secret

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

    # Read the prefect block for authentication
    PREFECT_BLOCK_AUTH: str = os.environ["PREFECT_BLOCK_AUTH"]
    try:
        secret = Secret.load(PREFECT_BLOCK_AUTH)
    except ValueError as error:
        if local_mode:
            raise ValueError(
                "In local mode, call prefect_utils.py::init_prefect_blocks() before this function.",
            ) from error
        else:
            raise ValueError(
                f"The Prefect secret block {PREFECT_BLOCK_AUTH!r} must be initialized manually "
                "before calling this function.",
            ) from error

    # In local mode, pass the username/password from the secret block
    if local_mode:
        auth = BasicAuth(**secret.get())

    # In cluster mode, init the jupyter hub authentication
    else:
        try:
            auth = JupyterHubAuth(secret.get()["JUPYTERHUB_API_TOKEN"])
        except KeyError as error:
            raise KeyError(
                f"'JUPYTERHUB_API_TOKEN' dict key is missing from the Prefect secret block: {PREFECT_BLOCK_AUTH!r}",
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

    # If a cluster has already been initialized, retrieve it
    if clusters := gateway.list_clusters():
        cluster = gateway.connect(clusters[0].name)

    # Else create one
    elif local_mode:
        cluster = gateway.new_cluster()
    else:  # cluster_mode
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

    # Forward logging from dask workers to the caller.
    # NOTE: we need to use the logging in the workers, "print" won't be forwarded.
    client.forward_logging()

    return gateway, cluster, client


def init_dask_cluster_staging(scale: int, *args, **kwargs):
    """Init existing staging dask cluster or create one"""
    global dask_gateway_staging, dask_cluster_staging, dask_client_staging
    dask_gateway_staging, dask_cluster_staging, dask_client_staging = init_dask_cluster(
        os.environ["DASK_GATEWAY_STAGING_ADDRESS"],
        os.environ["DASK_GATEWAY_STAGING_PUBLIC"],
        scale,
        image="ghcr.io/rs-python/rs-infrastructure-dask-gateway:latest",
        cluster_tag="dask-staging",
        *args,
        **kwargs,
    )


def init_dask_cluster_eopf(scale: int, *args, **kwargs):
    """Init existing eopf dask cluster or create one"""
    global dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf
    dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf = init_dask_cluster(
        os.environ["DASK_GATEWAY_EOPF_ADDRESS"],
        os.environ["DASK_GATEWAY_EOPF_PUBLIC"],
        scale,
        image="ghcr.io/rs-python/rs-infrastructure-dask-gateway/eopf:latest",  # TODO: TO BE DEFINED
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


def shutdown_dask_clusters(gateway: Gateway):
    """Shutdown all gateway clusters"""
    for cluster_info in gateway.list_clusters():
        try:
            cluster = gateway.connect(cluster_info.name)
            cluster.shutdown()
            print(f"Shutting down cluster {cluster_info.name!r} ...")
        except Exception as e:
            print(f"Error shutting down cluster {cluster_info.name!r}: {e}")
