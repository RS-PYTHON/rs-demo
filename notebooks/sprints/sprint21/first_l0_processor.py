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

import json
import os
import os.path as osp
import re
import subprocess
import sys
import time
from pathlib import Path

from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner
from rs_client.auxip_client import AuxipClient
from rs_client.cadip_client import CadipClient
from rs_client.catalog_client import CatalogClient
from rs_client.staging_client import StagingClient

# My local "./resources" folder contains my utility modules.
# I want to be able to use the same "from dask_utils import ..." line on both client, prefect and dask workers.
# For this, I'm updating my PYTHONPATH.
sys.path.append("./resources")
import dask_utils
import prefect_utils

# Convert the prefect blocks into environment variables for the S3 bucket and authentication.
prefect_utils.blocks_to_env_vars(_sync=True)

# Get the existing dask cluster info from the env vars passed by the client.
dask_cluster_name = os.environ["DASK_CLUSTER_NAME"]
dask_gateway, dask_cluster, dask_client = dask_utils.get_existing_cluster(
    os.environ["DASK_GATEWAY_ADDRESS"],
    dask_cluster_name,
)

# Now I need to upload my local utility module that will be used by the dask tasks
dask_client.upload_file("./resources/prefect_utils.py")

# Save the caller (=the prefect) env vars and variables, to be used by the dask tasks.
# These lines of code is not called by the dask workers.
caller_env = os.environ
local_mode = prefect_utils.local_mode

# In local mode, the service URLs are hardcoded in the docker-compose file
if local_mode:
    rs_server_href = None  # not used
# In cluster mode, they are set in an environment variables
else:
    rs_server_href = os.environ["RSPY_WEBSITE"]

# TEMP: EOPF changes the number of dask workers but we want to keep the current number
# See: https://gitlab.eopf.copernicus.eu/cpm/eopf-cpm/-/issues/680
worker_count = len(dask_client.scheduler_info()["workers"])

# NOTE: the tasks called with .submit() are called only by the dask workers, not by the client or prefect.
# Others tasks are called by the client or prefect.


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

    # Call some dummy auxip/cadip/staging tasks.
    # NOTE 1: call them without .submit so they are run by prefect nodes, not dask nodes
    # NOTE 2: maybe we could init a generic RsClient object from the flow and pass it to the tasks.
    # But I think (to be confirmed) that it will be serialized/deserialized so this is not optimized.
    staging_has_finished = dummy_staging(
        "",
        dummy_auxip_search("", "ADGS"),
        dummy_cadip_search("", "CADIP"),
    )

    # Setup adaptive scaling
    dask_gateway.adapt_cluster(dask_cluster_name, minimum=1, maximum=worker_count)

    # Run the EOPF task with .submit in a dask node
    eopf_has_finished = {}  # all_my_eopf_code.submit(
    #     staging_has_finished,
    #     input_config_dir,
    #     payload_file,
    #     output_data_dir,
    # ).result()

    # Call dummy catalog task
    return dummy_catalog_save(eopf_has_finished, "", "")


@task
def dummy_auxip_search(
    rs_server_api_key: str,
    station: str,
):
    """
    Dummy cadip search.

    NOTES:
      - station and rs_server_api_key should be given by the user as flow run parameters
    """
    logger = get_run_logger()
    logger.info("Start auxip search")
    time.sleep(1)  # this task should run in parallel with cadip
    AuxipClient(rs_server_href, rs_server_api_key, None, station)
    logger.info(f"End (dummy) auxip search")
    return {}


@task
def dummy_cadip_search(
    rs_server_api_key: str,
    station: str,
):
    """
    Dummy cadip search.

    NOTES:
      - station and rs_server_api_key should be given by the user as flow run parameters
    """
    logger = get_run_logger()
    logger.info("Start cadip search")
    time.sleep(1)  # this task should run in parallel with auxip
    CadipClient(rs_server_href, rs_server_api_key, None, station)
    logger.info(f"End (dummy) cadip search")
    return {}


@task
def dummy_staging(rs_server_api_key: str, *_):
    """
    Dummy cadip search.

    NOTES:
      - rs_server_api_key should be given by the user as flow run parameters
    """
    logger = get_run_logger()
    logger.info("Start staging")
    time.sleep(1)
    StagingClient(rs_server_href, rs_server_api_key, None)
    logger.info(f"End (dummy) staging search")
    return {}


@task
def dummy_catalog_save(_, rs_server_api_key: str, owner_id: str):
    """
    Dummy cadip search.

    NOTES:
      - owner_id and rs_server_api_key should be given by the user as flow run parameters
    """
    logger = get_run_logger()
    logger.info("Start catalog saving")
    time.sleep(1)
    CatalogClient(rs_server_href, rs_server_api_key, owner_id)
    logger.info(f"End (dummy) catalog saving:")
    return {}


@task
def all_my_eopf_code(
    _,
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
):
    # NOTE: not sure this is useful so I'm removing it
    # with worker_client(separate_thread=False)

    logger = get_run_logger()

    # Output report dir
    report_dirname = "reports"

    # Use env vars from the caller
    for key in [
        "S3_ACCESSKEY",
        "S3_SECRETKEY",
        "S3_ENDPOINT",
        "S3_REGION",
        "DASK_GATEWAY_ADDRESS",
        "DASK_CLUSTER_NAME",
    ] + (
        ["LOCAL_DASK_USERNAME", "LOCAL_DASK_PASSWORD"]
        if local_mode
        else ["JUPYTERHUB_API_TOKEN"]
    ):
        os.environ[key] = caller_env[key]

    # Also save the given output dir as an env var
    os.environ["OUTPUT_DIR"] = output_data_dir

    # Payload parent dir and filename
    payload_dir = osp.dirname(payload_file)
    payload_name = osp.basename(payload_file)

    # Download the input config dir locally
    # NOTE: maybe we should only download the payload file + only necessary config files
    # rather than the whole directory.
    local_config_dir = "config"
    prefect_utils.s3_download_dir(input_config_dir, local_config_dir)

    # Change working directory
    os.chdir(osp.join(local_config_dir, payload_dir))

    # Create the reports dir
    os.makedirs(report_dirname, exist_ok=True)

    # Hack the payload file
    hack_payload(payload_name)

    # Trigger EOPF processing, catch output
    p = subprocess.Popen(
        ["eopf", "trigger", "local", payload_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Write output to a log file + redirect to the prefect logger
    with open(
        osp.join(report_dirname, Path(payload_file).with_suffix(".log").name),
        "w+",
    ) as opened:
        while (line := p.stdout.readline()) != "":

            # The log prints password in clear e.g 'key': '<my-secret>'... hide them with a regex
            for key in (
                "key",
                "secret",
                "endpoint_url",
                "region_name",
                "api_token",
                "password",
            ):
                line = re.sub(rf"(\W{key}\W)[^,}}]*", r"\1: ***", line)

            # Write to log file
            opened.write(line)

            # Write to prefect logger if not empty
            line = line.rstrip()
            if line:
                logger.info(line)

    try:
        # Wait for the execution to finish
        status_code = p.wait()

        # Raise exception if the status code is != 0
        if status_code:
            raise Exception("EOPF error, please see the log.")

    # In all cases, upload the reports dir to the s3 bucket.
    finally:
        try:
            prefect_utils.s3_upload_dir(
                report_dirname,
                osp.join(output_data_dir, report_dirname),
            )
        except Exception as exception:
            logger.error(exception)

    # Dummy output for prefect
    return {}


@task
def hack_payload(filename: str):
    """Hack the payload file"""
    import yaml
    from dotenv import dotenv_values  # used in local mode only

    # Open the input yaml file
    with open(filename, "r", encoding="utf-8") as opened:
        payload = yaml.safe_load(opened)
    cluster_config = payload["dask_context"]["cluster_config"]

    # Set the number of workers
    cluster_config["workers"] = worker_count

    # We need to create the output S3 folder with a dummy file before running DPR
    for output_product in payload["I/O"]["output_products"]:
        output_dir = os.path.expandvars(output_product["path"])  # expand env vars
        prefect_utils.s3_upload_empty_file(f"{output_dir}/.empty")

    # Change the dask authentication for local mode
    if local_mode:
        cluster_config["auth"] = cluster_config["auth_local_mode"]
    del cluster_config["auth_local_mode"]

    # In local mode, open the user's s3cmd config file to use the cluster s3 bucket access.
    # It is mounted by the docker-compose.yml
    if local_mode:
        if not (k8s_access := dotenv_values("/.s3cfg")):
            raise Exception(
                "You must have a s3cmd config file under '~/.s3cfg' to use this flow",
            )
        os.environ.update(
            {
                "S3_ACCESSKEY_K8S": k8s_access["access_key"],
                "S3_SECRETKEY_K8S": k8s_access["secret_key"],
                "S3_ENDPOINT_K8S": k8s_access["host_bucket"],
                "S3_REGION_K8S": k8s_access["bucket_location"],
            },
        )
    # Change the bucket accees
    for input_product in payload["I/O"]["input_products"]:
        store_params = input_product["store_params"]
        if local_mode:
            store_params["storage_options"] = store_params["storage_options_local_mode"]
        del store_params["storage_options_local_mode"]

    # Write back the payload contents
    with open(filename, "w", encoding="utf-8") as opened:
        yaml.dump(payload, opened, default_flow_style=False, sort_keys=False)
