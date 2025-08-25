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
import re
import socket
import tempfile
import time
import zipfile
from pathlib import Path

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
    cluster_tag: str = "",
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
        cluster_tag: cluster name: "dask-staging" or "dask-eopf"
        worker_cores: number of worker cores
        worker_memory: worker memory in GB
        namespace: dask gateway namespace
        kwargs: additional keywoard arguments to pass to the method "gateway.new_cluster"
    """
    print(f"Connecting to dask gateway for {cluster_tag!r}: {address} ...")
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

        # In local mode, just get the first existing cluster.
        if local_mode:
            existing = clusters[0].name

        # In cluster mode, also check the docker image name and cluster name
        else:
            existing = next(
                (
                    report.name
                    for report in clusters
                    if (report.options.get("image") == image)
                    and (report.options.get("cluster_name") == cluster_tag)
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
            cluster_max_workers=scale + 1,
            cluster_max_cores=(scale + 1) * worker_cores,
            cluster_max_memory=(scale + 1) * worker_memory * (2**30),  # from GB to B
            scheduler_memory_limit=scheduler_memory_limit,
            namespace=namespace,
            image=image,
            cluster_name=cluster_tag,
            scheduler_extra_pod_labels={"cluster_name": cluster_tag},
            **kwargs,
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
    return gateway, cluster, client


def init_dask_cluster_staging(
    scale: int,
    image: str = "ghcr.io/rs-python/rs-infra-core-dask-staging:latest",
    *args,
    **kwargs,
):
    """Init existing staging dask cluster or create one"""
    global dask_gateway_staging, dask_cluster_staging, dask_client_staging

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
        **(dpr_tuning | kwargs),  # set default DPR tuning
    )


def init_dask_cluster_eopf(
    scale: int,
    processor_name: str = "l0",
    processor_code: str = "S1L0",  # S1L0, S3L0 or S1ARD
    image: str = "ghcr.io/rs-python/rs-infra-core-dask-eopf:latest",
    use_mockup=False,
    *args,
    **kwargs,
):
    """Init existing eopf dask cluster or create one"""
    global dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf
    local_environ_eopf_address = f"DASK_GATEWAY_{processor_code}_ADDRESS"
    local_environ_eopf_public = f"DASK_GATEWAY_{processor_code}_PUBLIC"
    cluster_tag = f"dask-{processor_name}"

    if use_mockup:
        image = "ghcr.io/rs-python/rs-infra-core-dask-eopf-mockup:latest"
        local_environ_eopf_address = "DASK_GATEWAY_EOPF_MOCKUP_ADDRESS"
        local_environ_eopf_public = "DASK_GATEWAY_EOPF_MOCKUP_PUBLIC"
        cluster_tag = "dask-eopf-mockup"
        dpr_tuning = {}

    # Additional arguments to pass to the DPR cluster.
    # See: https://github.com/RS-PYTHON/rs-infra-core/blob/develop/docs/how-to/Dask-gateway.md
    else:
        dpr_tuning = {
            "scheduler_memory_limit": 60,  # In GB
            "worker_extra_pod_config": {
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
            },
            "scheduler_extra_pod_config": {
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
            },
        }

    dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf = init_dask_cluster(
        (
            os.environ["DASK_GATEWAY_ADDRESS"]
            if cluster_mode
            else os.environ[local_environ_eopf_address]
        ),
        (
            os.environ["DASK_GATEWAY_PUBLIC"]
            if cluster_mode
            else os.environ[local_environ_eopf_public]
        ),
        scale,
        image=image,
        cluster_tag=cluster_tag,
        *args,
        **(dpr_tuning | kwargs),  # set default DPR tuning
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
    global dask_client_staging, dask_client_eopf, dask_cluster_staging, dask_cluster_eopf, dask_gateway_staging, dask_gateway_eopf

    # First client, then cluster, then gateway
    for obj in (
        dask_client_staging,
        dask_client_eopf,
        dask_cluster_staging,
        dask_cluster_eopf,
        dask_gateway_staging,
        dask_gateway_eopf,
    ):
        if obj:
            obj.close()

    dask_client_staging = None
    dask_client_eopf = None
    dask_cluster_staging = None
    dask_cluster_eopf = None
    dask_gateway_staging = None
    dask_gateway_eopf = None


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


def upload_util_modules(clients: list[DaskClient]):
    """
    Upload utility modules from the caller (=prefect or jupyter) environment to dask clients.

    WARNING: These modules should not import other modules that are not installed in the dask
    environment or you'll have import errors.

    Args:
        clients: list of dask clients to which upload the modules.
    """

    # Root of the current project
    root = Path(__file__).parent.parent

    # Upload files from rs_common
    import rs_common

    rs_common_dir = Path(rs_common.__path__[0])

    # Files to upload and associated name in the zip archive
    files = {
        root / "resources/__init__.py": "resources/__init__.py",
        root / "resources/dask_utils.py": "resources/dask_utils.py",
        rs_common_dir / "__init__.py": "rs_common/__init__.py",
        rs_common_dir / "init_opentelemetry.py": "rs_common/init_opentelemetry.py",
        rs_common_dir / "logging.py": "rs_common/logging.py",
        rs_common_dir / "prefect_utils.py": "rs_common/prefect_utils.py",
        rs_common_dir / "utils.py": "rs_common/utils.py",
    }

    # From a temp dir
    with tempfile.TemporaryDirectory() as tmpdir:

        # Create a zip with our files
        zip_path = f"{tmpdir}/rs-demo-resources.zip"
        with zipfile.ZipFile(zip_path, "w") as zipped:

            # Zip all files
            for key, value in files.items():
                zipped.write(str(key), str(value))

        # Upload zip file to dask clients.
        # This also installs the zipped modules inside the dask python interpreter.
        for client in clients:
            client.upload_file(zip_path)


def copy_caller_env(caller_env: dict[str, str]):
    """
    Copy environment variables from caller (=prefect or jupyter) environment.

    Args:
        caller_env: os.environ coming from caller
    """

    # Update the local/clsuter mode global variable with the env var coming from the caller
    global local_mode, cluster_mode
    local_mode = caller_env.get("RSPY_LOCAL_MODE") == "1"
    cluster_mode = not local_mode

    # Copy env vars from the caller
    keys = [
        "RSPY_LOCAL_MODE",
        "S3_ACCESSKEY",
        "S3_SECRETKEY",
        "S3_ENDPOINT",
        "S3_REGION",
        "PREFECT_BUCKET_NAME",
        "PREFECT_BUCKET_FOLDER",
        "DASK_CLUSTER_EOPF_NAME",
        "AWS_REQUEST_CHECKSUM_CALCULATION",
        "AWS_RESPONSE_CHECKSUM_VALIDATION",
        "TEMPO_ENDPOINT",
        "OTEL_PYTHON_REQUESTS_TRACE_HEADERS",
        "OTEL_PYTHON_REQUESTS_TRACE_BODY",
    ]
    if local_mode:
        keys.extend(
            [
                "LOCAL_DASK_USERNAME",
                "LOCAL_DASK_PASSWORD",
                "access_key",
                "bucket_location",
                "host_base",
                "host_bucket",
                "secret_key",
            ],
        )

        # List the environment variables available containing adresses to processor clusters
        processor_address_pattern = re.compile(r"^DASK_GATEWAY_([A-Za-z0-9]+)_ADDRESS$")
        processor_env_vars = [
            var for var in caller_env if processor_address_pattern.match(var)
        ]
        keys.extend(processor_env_vars)
    else:
        keys.extend(["JUPYTERHUB_API_TOKEN", "DASK_GATEWAY__ADDRESS"])
    for key in keys:
        if value := caller_env.get(key):
            os.environ[key] = value
