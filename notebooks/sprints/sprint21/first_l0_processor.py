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
from dask_utils import get_ip_address

# Convert the prefect blocks into environment variables.
# This gives us the env vars: S3_ACCESSKEY, S3_SECRETKEY, S3_ENDPOINT, S3_REGION
prefect_utils.blocks_to_env_vars(_sync=True)


@flow
def first_l0_processor(
    input_config_folder: str,
    payload_file: str,
    output_data_folder: str,
):
    """
    Trigger an EOPF L0 processing.

    This is a pure prefect flow. The EOPF triggering is run in command-line,
    it is responsible of distributing its work in the dask workers.

    Args:
        input_config_folder: s3 bucket folder that contains the configuration files (NOT THE VOLUMINOUS DATA !).
        It will be downloaded locally.
        payload_file: input yaml configuration file to pass to the triggering. Local to the 'input_config_folder'.
        output_data_folder: s3 bucket folder that will contain the generated data.
    """

    logger = get_run_logger()
    logger.warning(
        f"Hello from {os.environ['HELLO_FROM']!r} {get_ip_address()!r} (flow)",
    )

    # Call the task for each output filename
    futures = [
        single_dpr_task.submit(
            logger,
            s3_folder,
            filename,
        )
        for filename in s3_filenames
    ]

    # We should do this
    return [future.result(timeout=10) for future in futures]

    # # Workaround to try several times... to be removed
    # results = []
    # for future in futures:
    #     tries = 0
    #     while True:
    #         try:
    #             tries += 1
    #             logger.info(f"Try #{tries}")
    #             results.append(future.result(timeout=10))
    #             break
    #         except Exception as exception:
    #             if tries >= 5:
    #                 raise
    #             logger.error(exception)

    return results
