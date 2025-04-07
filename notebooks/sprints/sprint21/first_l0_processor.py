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

import os
import os.path as osp
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
import rs_common
import rs_common.opentelemetry as rsotel
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact
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
dask_client.upload_file(f"{rs_common.__path__[0]}/opentelemetry.py")

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

# Opentelemetry configuration
tracer = trace.get_tracer(__name__)
TEMPO_ENDPOINT = os.getenv("TEMPO_ENDPOINT")


##########################
# Prefect tasks and flow #
##########################


@flow
def first_l0_processor(
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
):
    """
    Trigger an EOPF L0 processing.

    Args:
        input_config_dir: s3 bucket directory that contains the configuration files (NOT THE VOLUMINOUS DATA !).
        It will be downloaded locally.
        payload_file: input yaml configuration file to pass to the triggering. Local to the 'input_config_dir'.
        output_data_dir: s3 bucket directory that will contain the generated data.
    """

    rsotel.init_traces("rs.client.prefect")

    tracer = trace.get_tracer(__name__)

    # Wrap all flow in an Opentelemetry flow
    with tracer.start_as_current_span("first_l0_processor_flow"):

        # Extract span infos to send to Dask
        flow_span_context = trace.get_current_span().get_span_context()

        test_req = requests.get("https://fr.wikipedia.org/wiki/Topinambour")

        # TODO: should be passed as user-given parameter
        rs_server_api_key = "my_api_key"
        adgs_station = "ADGS"
        cadip_station = "CADIP"
        owner_id = "my_owner_id"

        auxip_search_result = dummy_auxip_search.submit(rs_server_api_key, adgs_station)
        cadip_search_result = dummy_cadip_search.submit(
            rs_server_api_key,
            cadip_station,
        )

        # Call some dummy auxip/cadip/staging tasks.
        # NOTE: maybe we could init a generic RsClient object from the flow and pass it to the tasks.
        # But I think (to be confirmed) that it will be serialized/deserialized so this is not optimized.
        staging_result = dummy_staging.submit(
            rs_server_api_key,
            auxip_search_result,
            cadip_search_result,
        )

        config_file_result = dummy_config_file.submit(
            rs_server_api_key,
            auxip_search_result,
            cadip_search_result,
        )

        # Run the EOPF task with .submit in a dask node
        eopf_result = first_l0_processor_dask(
            flow_span_context.trace_id,
            flow_span_context.span_id,
            staging_result,
            config_file_result,
            input_config_dir,
            payload_file,
            output_data_dir,
        )

        # Call dummy catalog task
        catalog_result = dummy_catalog_save.submit(
            eopf_result,
            rs_server_api_key,
            owner_id,
        )
        return catalog_result.result()


@task
def dummy_auxip_search(
    rs_server_api_key: str,
    station: str,
):
    """Dummy auxip search."""
    logger = get_run_logger()
    logger.info("Start (dummy) auxip search")
    time.sleep(1)  # this task should run in parallel with cadip
    test_req = requests.get("https://fr.wikipedia.org/wiki/Val_Kilmer")
    # AuxipClient(rs_server_href, rs_server_api_key, None, station)
    logger.info(f"End (dummy) auxip search")
    return {}


@task
def dummy_cadip_search(
    rs_server_api_key: str,
    station: str,
):
    """Dummy cadip search."""
    logger = get_run_logger()
    logger.info("Start (dummy) cadip search")
    time.sleep(1)  # this task should run in parallel with auxip
    test_req = requests.get("https://fr.wikipedia.org/wiki/Copernicus_(programme)")
    # CadipClient(rs_server_href, rs_server_api_key, None, station)
    logger.info(f"End (dummy) cadip search")
    return {}


@task
def dummy_staging(rs_server_api_key: str, *_):
    """Dummy staging"""
    logger = get_run_logger()
    logger.info("Start (dummy) staging")
    time.sleep(1)
    test_req = requests.get("https://fr.wikipedia.org/wiki/Union_europ%C3%A9enne")
    # StagingClient(rs_server_href, rs_server_api_key, None)
    logger.info(f"End (dummy) staging search")
    return {}


@task
def dummy_config_file(rs_server_api_key: str, *_):
    """Dummy config file writing for the processor"""
    logger = get_run_logger()
    logger.info("Start (dummy) config file")
    time.sleep(1)
    logger.info(f"End (dummy) config file")
    return {}


@task
def dummy_catalog_save(eopf_result, rs_server_api_key: str, owner_id: str):
    """Dummy catalog call to save results"""
    logger = get_run_logger()
    logger.info("Start catalog saving")
    time.sleep(1)
    test_req = requests.get("https://fr.wikipedia.org/wiki/Sid_(L%27%C3%82ge_de_glace)")
    # CatalogClient(rs_server_href, rs_server_api_key, owner_id)
    logger.info(f"End (dummy) catalog saving:")
    return {}


#######################
# Dask tasks and flow #
#######################


@flow(
    task_runner=DaskTaskRunner(
        address=dask_cluster.scheduler_address,
        client_kwargs={"security": dask_cluster.security},
    ),
)
def first_l0_processor_dask(
    optl_trace_id,
    optl_span_id,
    staging_result,
    config_file_result,
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
):
    """
    Dask flow used to call tasks in dask workers.
    """
    return main_dask_task.submit(
        optl_trace_id,
        optl_span_id,
        input_config_dir,
        payload_file,
        output_data_dir,
    )


@task
async def main_dask_task(
    optl_trace_id: int,
    optl_span_id: int,
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
):
    # NOTE: not sure this is useful so I'm removing it
    # with worker_client(separate_thread=False)

    os.environ["TEMPO_ENDPOINT"] = TEMPO_ENDPOINT
    import opentelemetry as rsotel

    rsotel.init_traces("rs.client.dask")

    tracer = trace.get_tracer(__name__)

    main_span_context = SpanContext(
        trace_id=optl_trace_id,
        span_id=optl_span_id,
        is_remote=True,
        trace_flags=TraceFlags(0x01),
    )
    main_span = NonRecordingSpan(main_span_context)

    with trace.use_span(main_span):

        # Basic request to use as test tracker
        wiki_result = requests.get(
            "https://fr.wikipedia.org/wiki/Patrick_Balkany#Affaires_judiciaires",
        )

        with tracer.start_as_current_span("main_dask_flow"):

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
            await prefect_utils.s3_download_dir(input_config_dir, local_config_dir)

            # Change working directory
            os.chdir(osp.join(local_config_dir, payload_dir))

            # Create the reports dir
            os.makedirs(report_dirname, exist_ok=True)

            # Hack the payload file
            await hack_payload(payload_name)

            # Trigger EOPF processing, catch output
            p = subprocess.Popen(
                ["eopf", "trigger", "local", payload_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Log contents
            log_str = ""

            # Write output to a log file and string + redirect to the prefect logger
            with open(
                osp.join(report_dirname, Path(payload_file).with_suffix(".log").name),
                "w+",
            ) as log_file:
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

                    # Write to log file and string
                    log_file.write(line)
                    log_str += line

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
                    await prefect_utils.s3_upload_dir(
                        report_dirname,
                        osp.join(output_data_dir, report_dirname),
                    )
                except Exception as exception:
                    logger.error(exception)

                # Save log str into a markdown artifact
                create_markdown_artifact(
                    key="logging",
                    markdown=f"```\n{log_str}\n```",
                    description="L0 processing logging",
                )

            # Dummy output for prefect
            return {}


@task
async def hack_payload(filename: str):
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
        await prefect_utils.s3_upload_empty_file(f"{output_dir}/.empty")

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
