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
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from botocore.utils import calculate_md5
from fastapi.concurrency import run_in_threadpool
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

# Prefect S3 objects for each bucket.
S3_BUCKETS: dict[str, S3Bucket] = {}


def get_block_auth_user():
    """
    Return the prefect block name that contains the authentication
    specific to one user = the api key or oauth2 cookie.
    """
    if local_mode:
        owner_id = os.environ["RSPY_HOST_USER"]
    else:  # cluster mode
        owner_id = os.environ["JUPYTERHUB_USER"]

    # NOTE: for now all prefect users share their blocks and secrets, but later this will not be the case anymore.
    return f"auth-user-{owner_id.lower()}"


def get_ip_address() -> str:
    """Return IP address, see: https://stackoverflow.com/a/166520"""
    return socket.gethostbyname(socket.gethostname())


@sync_compatible
async def read_block(cls, name: str):
    """Read a prefect block, add an error message around."""
    try:
        return await cls.load(name)
    except ValueError as error:
        if local_mode:
            raise ValueError(
                "In local mode, call prefect_utils.py::init_prefect_blocks() before this function.",
            ) from error
        else:
            raise ValueError(
                f"The Prefect secret block {name!r} must be initialized manually before calling this function.",
            ) from error


@sync_compatible
async def read_apikey(optional: bool = True, save_to_env: bool = True) -> None:
    """
    Read the API key, either from the environment variable or from an interactive input form.

    Args:
        optional (bool): If False and if the env var is missing, ask it from an interactive input form.
        save_to_env (bool): If True, saves the API key to the ~/.env file.

    NOTE: don't return the apikey value because there is a risk that it is displayed in the
    notebook (if this function is called from the last cell line) so this is not secured.
    """
    global apikey

    # No API key in local mode
    if local_mode:
        return

    # If the API is saved as an env var in the ~/.env file, then it has already
    # been read automatically by rs-infra-core/.github/jupyter/resources/00-read-env.py
    apikey = os.getenv("RSPY_APIKEY")
    if (not apikey) and (not optional):

        # Else read it from user input
        apikey = getpass.getpass(f"Enter your API key:")

        # Save the env var
        os.environ["RSPY_APIKEY"] = apikey

        # Append it to the ~/.env file, if requested.
        # Don't overwrite the full ~/.env file because it can contain other user info.
        if save_to_env:
            with open(os.path.expanduser("~/.env"), "a") as env_file:
                env_file.write(f"\nRSPY_APIKEY={apikey}\n")
                print("API key saved to ~/.env.")


@sync_compatible
async def init_prefect_blocks():
    global PREFECT_BLOCK_S3
    block_auth = os.environ["PREFECT_BLOCK_AUTH"]
    block_s3 = os.environ["PREFECT_BLOCK_S3"]

    # Create the blocks in local mode.
    # In the cluster, the blocks must be created only once by the admin.
    if local_mode:

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
            await secret.save(block_auth, overwrite=True)
        except ValueError:  # do nothing if the block was already saved
            pass

        # Share data between the user, the client (jupyter or terminal) and prefect
        aws_credentials = AwsCredentials(
            aws_access_key_id=os.environ["S3_ACCESSKEY"],
            aws_secret_access_key=os.environ["S3_SECRETKEY"],
            region_name=os.environ["S3_REGION"],
            aws_client_parameters={"endpoint_url": os.environ["S3_ENDPOINT"]},
        )
        PREFECT_BLOCK_S3 = S3Bucket(
            bucket_name=os.environ["RSPY_TEMP_BUCKET"],
            credentials=aws_credentials,
            bucket_folder="sub/dir",
        )
        await PREFECT_BLOCK_S3.save(block_s3, overwrite=True)

    # In cluster mode
    else:
        # Read the rspy api key
        await read_apikey()

        # In a prefect secret block, save the user authentication = api key and oauth2 cookie
        auth_user = {"RSPY_OAUTH2_COOKIE": os.environ["RSPY_OAUTH2_COOKIE"]}

        # Add the api key, if present
        if apikey:
            auth_user["RSPY_APIKEY"] = apikey

        # Save the prefect secret block
        await Secret(value=auth_user).save(get_block_auth_user(), overwrite=True)

    # Save the dask authentication from prefect blocks as env vars
    await blocks_to_env_vars()


@sync_compatible
async def blocks_to_env_vars():
    """
    Convert the prefect blocks into environment variables.
    """
    global PREFECT_BLOCK_S3

    # Prefect block names
    block_auth = os.environ.get("PREFECT_BLOCK_AUTH")
    block_s3 = os.environ["PREFECT_BLOCK_S3"]

    #
    # Auth block

    # Read the prefect block for authentication
    auth: dict = (await read_block(Secret, block_auth)).get()

    # In cluster mode, make sure it has the right keys.
    # Don't do it in local mode, the keys are set internally by init_prefect_blocks()
    if cluster_mode and ("JUPYTERHUB_API_TOKEN" not in auth):
        raise KeyError(
            f"'JUPYTERHUB_API_TOKEN' dict key is missing from the Prefect secret block: {block_auth!r}",
        )

    # Save auth keys/values into env vars
    os.environ.update(auth)

    #
    # S3 block

    # Update the S3 bucket env vars from the block info.
    # NOTE: in fact in local mode, the prefect block was already initialized from these env vars.
    # But it's still useful to do this from a prefect flow so we pass only the block to the flow, not the env vars.
    PREFECT_BLOCK_S3 = await read_block(S3Bucket, block_s3)
    os.environ.update(
        {
            "S3_ACCESSKEY": PREFECT_BLOCK_S3.credentials.aws_access_key_id,
            "S3_SECRETKEY": PREFECT_BLOCK_S3.credentials.aws_secret_access_key.get_secret_value(),
            "S3_REGION": PREFECT_BLOCK_S3.credentials.region_name,
            "S3_ENDPOINT": PREFECT_BLOCK_S3.credentials.aws_client_parameters.endpoint_url,
            "S3_BUCKET_NAME": PREFECT_BLOCK_S3.bucket_name,
            "S3_BUCKET_FOLDER": PREFECT_BLOCK_S3.bucket_folder,
        },
    )

    #
    # User authentication = api key and oauth2 cookie

    # Only for cluster mode. Don't overwrite existing environment, if any.
    if cluster_mode:
        auth_user = (await read_block(Secret, get_block_auth_user())).get()
        for key, value in auth_user.items():
            if key not in os.environ:
                os.environ[key] = value


def hack_for_jupyter(func: Callable, *args, **kwargs) -> asyncio.Task:
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


#
# Utility functions for s3 bucket operations.


def get_s3_bucket(s3_path: str) -> tuple[S3Bucket, str]:
    """
    Return a prefect S3 bucket object and S3 "object name" (= S3 path without s3://bucket-name)
    from the given S3 path.
    We use the prefect higher-level functions instead of those from boto3.
    Maybe this is not optimized and we should use boto3 instead... but it's only for the demos.
    """

    # Remove the s3:// prefix and split by /
    split = s3_path.removeprefix("s3").removeprefix("S3").strip(":/").split("/")

    # Filter empty elements (if we had double //)
    split = list(filter(None, split))

    if not split:
        raise Exception(f"Invalid S3 path: {s3_path!r}")

    bucket_name = split[0]
    object_name = "/".join(split[1:])

    # Init a new prefect object for this bucket, or create a new one
    # with the same credentials as the configured one, with no prefixed folder.
    try:
        return S3_BUCKETS[bucket_name], object_name
    except KeyError:
        aws_credentials = AwsCredentials(
            aws_access_key_id=os.environ["S3_ACCESSKEY"],
            aws_secret_access_key=os.environ["S3_SECRETKEY"],
            region_name=os.environ["S3_REGION"],
            aws_client_parameters={"endpoint_url": os.environ["S3_ENDPOINT"]},
        )
        s3_bucket = S3Bucket(
            bucket_name=bucket_name,
            credentials=aws_credentials,
            bucket_folder="",
        )
        S3_BUCKETS[bucket_name] = s3_bucket
        return s3_bucket, object_name


@sync_compatible
async def s3_upload_file(
    from_path: Union[str, Path],
    s3_path: str,
    **upload_kwargs: Dict[str, Any],
) -> str:
    """See: S3Bucket.upload_from_path"""
    s3_bucket, to_path = get_s3_bucket(s3_path)
    return await s3_bucket.upload_from_path(from_path, to_path, **upload_kwargs)


@sync_compatible
async def s3_upload_empty_file(
    s3_path: str,
    **upload_kwargs: Dict[str, Any],
) -> str:
    """Upload an empty temp file to the S3 bucket."""

    # Create a tmp file
    with tempfile.NamedTemporaryFile() as tmp:

        # Add contents to the file or boto3 has a strange behavior after uploading an empty file
        tmp.write(b"empty")
        tmp.flush()

        # Upload the file
        return await s3_upload_file(tmp.name, s3_path, **upload_kwargs)


@sync_compatible
async def s3_upload_dir(
    from_folder: Union[str, Path],
    s3_path: str,
    **upload_kwargs: Dict[str, Any],
) -> Union[str, None]:
    """
    See: S3Bucket.upload_from_folder

    Uploads files *within* a folder (excluding the folder itself) to the object storage service folder.
    """
    s3_bucket, to_path = get_s3_bucket(s3_path)
    return await s3_bucket.upload_from_folder(from_folder, to_path, **upload_kwargs)


@sync_compatible
async def s3_download_file(
    s3_path: str,
    to_path: Optional[Union[str, Path]],
    **download_kwargs: Dict[str, Any],
) -> Path:
    """See: S3Bucket.download_object_to_path"""
    s3_bucket, from_path = get_s3_bucket(s3_path)
    await s3_bucket.download_object_to_path(from_path, to_path, **download_kwargs)


@sync_compatible
async def s3_download_dir(
    s3_path: str,
    local_path: Optional[str] = None,
) -> None:
    """See: S3Bucket.get_directory"""
    s3_bucket, from_path = get_s3_bucket(s3_path)
    await s3_bucket.get_directory(from_path, local_path)


def s3_delete(s3_prefix: str):
    """Remove all files from S3 bucket with the given prefix, using low-level client and Content-MD5 header."""
    s3_bucket, prefix = get_s3_bucket(s3_prefix)
    if not prefix.endswith("/"):
        prefix += "/"
    objects_to_delete = [
        {"Key": obj.key}
        for obj in s3_bucket._get_bucket_resource().objects.filter(Prefix=prefix)
    ]

    if not objects_to_delete:
        return

    # Hook to compute Content-MD5 from actual serialized body
    def inject_md5_on_real_payload(request, **kwargs):
        request.headers["Content-MD5"] = calculate_md5(request.body)

    s3_client = s3_bucket._get_s3_client()
    s3_client.meta.events.register(
        "before-sign.s3.DeleteObjects",
        inject_md5_on_real_payload,
    )

    return s3_client.delete_objects(
        Bucket=s3_bucket.bucket_name,
        Delete={"Objects": objects_to_delete, "Quiet": True},
    )
