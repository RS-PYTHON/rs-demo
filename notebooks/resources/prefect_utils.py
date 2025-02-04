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

"""Utility Python module for the tutorials, to be shared with the prefect or dask workers.

WARNING: AFTER EACH MODIFICATION, RESTART THE JUPYTER NOTEBOOK KERNEL !
"""

import asyncio
import getpass
import os
import secrets
import socket
import typing

from fastapi.concurrency import run_in_threadpool
from prefect.blocks.system import JSON as JsonBlock
from prefect.blocks.system import Secret
from prefect.client.orchestration import get_client
from prefect.exceptions import ObjectNotFound
from prefect.utilities.asyncutils import sync_compatible
from prefect_aws import AwsCredentials, S3Bucket

# In local mode, all your services are running locally.
# In cluster mode, we use the services deployed on the RS-Server website.
# This configuration is set in an environment variable.
local_mode: bool = os.getenv("RSPY_LOCAL_MODE") == "1"
cluster_mode: bool = not local_mode

# Prefect blocks
PREFECT_BLOCK_S3: S3Bucket = None


def get_ip_address() -> str:
    """Return IP address, see: https://stackoverflow.com/a/166520"""
    return socket.gethostbyname(socket.gethostname())


@sync_compatible
async def init_prefect_blocks():
    global PREFECT_BLOCK_S3

    # This is only for local mode.
    # In the cluster, the blocks must be created only once by the admin.
    if not local_mode:
        return

    # Save authentication as a secret to connect to the Dask gateway.
    # In local mode, use username/password.
    # In cluster mode, it should contain {"JUPYTERHUB_API_TOKEN": "<value>"}
    # We generate a random password and save the block only once (overwrite=False).
    # Maybe this is overkill and we could just use a hardcoded password in local mode.
    try:
        secret = Secret(
            value={
                "LOCAL_DASK_USERNAME": os.environ["RSPY_HOST_USER"],
                "LOCAL_DASK_PASSWORD": secrets.token_urlsafe(32),
            },
        )
        await secret.save(os.environ["PREFECT_BLOCK_AUTH"], overwrite=True)
    except ValueError:  # do nothing if the block was already saved
        pass

    # Save the dask authentication from prefect blocks as env vars
    await save_auth_env()

    # Share data between the user, the client (jupyter or terminal) and prefect
    aws_credentials = AwsCredentials(
        aws_access_key_id=os.environ["S3_ACCESSKEY"],
        aws_secret_access_key=os.environ["S3_SECRETKEY"],
        region_name=os.environ["S3_REGION"],
        aws_client_parameters={"endpoint_url": os.environ["S3_ENDPOINT"]},
    )
    PREFECT_BLOCK_S3 = S3Bucket(
        bucket_name=os.environ["PREFECT_SHARE_BUCKET"],
        credentials=aws_credentials,
        bucket_folder="sub/dir",
    )
    await PREFECT_BLOCK_S3.save(os.environ["PREFECT_BLOCK_S3"], overwrite=True)


@sync_compatible
async def save_auth_env():
    """
    We need the auth block values to connect to the dask cluster.
    We pass these values as env vars because some systems that use dask
    may not have prefect installed to read from the blocks.
    """

    # Read the prefect block for authentication
    PREFECT_BLOCK_AUTH: str = os.environ["PREFECT_BLOCK_AUTH"]
    try:
        secret = await Secret.load(PREFECT_BLOCK_AUTH)
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

    # In cluster mode, make sure it has the right keys.
    # Don't do it in local mode, the keys are set internally by init_prefect_blocks()
    auth = secret.get()
    if cluster_mode and ("JUPYTERHUB_API_TOKEN" not in auth):
        raise KeyError(
            f"'JUPYTERHUB_API_TOKEN' dict key is missing from the Prefect secret block: {PREFECT_BLOCK_AUTH!r}",
        )

    # Save auth keys/values into env vars
    os.environ.update(auth)


def hack_for_jupyter(func: typing.Callable, *args, **kwargs) -> asyncio.Task:
    """From Jupyter we need this hack to deploy prefect flows"""
    coroutine = run_in_threadpool(func, *args, **kwargs)
    return asyncio.create_task(coroutine)


async def wait_for_deployment(name: str, wait=1, max_retry=30):
    """Wait for prefect deployment to be finished."""
    # Taken from prefect/cli/deployment.py::inspect
    retry = 0
    async with get_client() as client:
        while True:
            try:
                await client.read_deployment_by_name(name)
                print(f"Finished deploying prefect flow: {name!r}")
                return
            except ObjectNotFound:
                retry += 1
                if retry >= max_retry:
                    raise
                print(f"Wait for deployment of prefect flow: {name!r} ...")
                await asyncio.sleep(wait)
