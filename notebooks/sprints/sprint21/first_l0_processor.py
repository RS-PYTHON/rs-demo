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

"""First L0 processor"""

import logging
import os
import os.path as osp
import sys
from pathlib import Path

from distributed import worker_client
from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner

# My local "./resources" folder contains my utility modules.
# I want to be able to use the same "from dask_utils import ..." line on both client, prefect and dask workers.
# For this, I'm updating my PYTHONPATH.
sys.path.append("./resources")
import dask_utils
import prefect_utils

# Convert the prefect blocks into environment variables for the S3 bucket and authentication.
prefect_utils.blocks_to_env_vars(_sync=True)

# Get the existing dask cluster info from the env vars passed by the client.
dask_gateway, dask_cluster, dask_client = dask_utils.get_existing_cluster(
    os.environ["DASK_GATEWAY_ADDRESS"],
    os.environ["DASK_CLUSTER_NAME"],
)

# Now I need to upload my local utility module to the dask workers
dask_client.upload_file("./resources/dask_utils.py")


# Pass the environment variables to the dask client
def set_dask_env(prefect_env: dict):
    for key in [
        "S3_ACCESSKEY",
        "S3_SECRETKEY",
        "S3_ENDPOINT",
        "S3_REGION",
        "DASK_GATEWAY_ADDRESS",
        "DASK_CLUSTER_NAME",
        "JUPYTERHUB_API_TOKEN",
        "LOCAL_DASK_USERNAME",
        "LOCAL_DASK_PASSWORD",
    ]:
        os.environ[key] = prefect_env.get(key)


dask_client.run(set_dask_env, os.environ)

# NOTE: the tasks are called only by the dask workers, not by the client or prefect.


@task
def all_my_eopf_code(
    logger,
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
):
    """
    EOPF is installed only in the dask workers, so put all the "import eopf ..." lines in the task, not outside.
    """
    from eopf.cli import eopf_cli

    # NOTE: we need to create the S3 folder with a dummy file before running DPR
    prefect_utils.s3_upload_empty_file(f"{output_data_dir}/.empty")

    # Download the input config dir locally
    local_config_dir = "config"
    prefect_utils.s3_download_dir(input_config_dir, local_config_dir)

    # Change working directory
    os.chdir(osp.join(local_config_dir, osp.dirname(payload_file)))

    # Trigger EOPF processing
    sys.argv = [
        os.path.basename(__file__),
        "trigger",
        "local",
        osp.basename(payload_file),
    ]
    return eopf_cli()


@task
def single_dpr_task(*args, **kwargs):
    """
    Call the EOPF code.
    """
    with worker_client(separate_thread=False):  # as client:
        return all_my_eopf_code(*args, **kwargs)


@flow(
    task_runner=DaskTaskRunner(
        address=dask_cluster.scheduler_address,
        client_kwargs={"security": dask_cluster.security},
    ),
)
def first_l0_processor(
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
):
    """
    Trigger an EOPF L0 processing.

    This is a pure prefect flow. The EOPF triggering is run in command-line,
    it is responsible of distributing its work in the dask workers.

    Args:
        input_config_dir: s3 bucket directory that contains the configuration files (NOT THE VOLUMINOUS DATA !).
        It will be downloaded locally.
        payload_file: input yaml configuration file to pass to the triggering. Local to the 'input_config_dir'.
        output_data_dir: s3 bucket directory that will contain the generated data.
    """
    logger = get_run_logger()
    return single_dpr_task.submit(
        logger,
        input_config_dir,
        payload_file,
        output_data_dir,
    ).result()
