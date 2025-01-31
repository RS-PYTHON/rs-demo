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
import os
import secrets
import socket
import typing

from fastapi.concurrency import run_in_threadpool
from prefect.blocks.system import JSON as JsonBlock
from prefect.client.orchestration import get_client
from prefect.exceptions import ObjectNotFound
from prefect.filesystems import RemoteFileSystem

# In local mode, all your services are running locally.
# In cluster mode, we use the services deployed on the RS-Server website.
# This configuration is set in an environment variable.
local_mode: bool = os.getenv("RSPY_LOCAL_MODE") == "1"
cluster_mode: bool = not local_mode

RSPY_HOST_USER = os.environ["RSPY_HOST_USER"]
PREFECT_WORK_POOL = os.environ["PREFECT_WORK_POOL"]
PREFECT_SHARE_BUCKET = os.environ["PREFECT_SHARE_BUCKET"]

# Prefect blocks
PREFECT_BLOCK_S3: RemoteFileSystem = None


def get_ip_address() -> str:
    """Return IP address, see: https://stackoverflow.com/a/166520"""
    return socket.gethostbyname(socket.gethostname())


async def init_prefect_blocks():
    global PREFECT_BLOCK_S3

    # This is only for local mode.
    # In the cluster, the blocks must be created only once by the admin.
    if not local_mode:
        return

    # Save authentication to connect to the Dask gateway.
    # In local mode, use username/password.
    # In cluster mode, it should contain {"JUPYTERHUB_API_TOKEN": "<value>"}
    auth = JsonBlock(
        value={
            "username": RSPY_HOST_USER,
            "password": secrets.token_urlsafe(32),  # generate random password
        },
    )
    await auth.save(os.environ["PREFECT_BLOCK_AUTH"], overwrite=True)

    # Share data between the user, the client (jupyter or terminal) and prefect
    PREFECT_BLOCK_S3 = RemoteFileSystem(
        basepath=f"s3://{PREFECT_SHARE_BUCKET}",
        settings={
            "key": os.environ["S3_ACCESSKEY"],
            "secret": os.environ["S3_SECRETKEY"],
            "client_kwargs": {"endpoint_url": os.environ["S3_ENDPOINT"]},
        },
    )
    await PREFECT_BLOCK_S3.save(os.environ["PREFECT_BLOCK_S3"], overwrite=True)


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
