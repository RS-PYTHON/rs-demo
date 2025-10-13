# Copyright 2025 CS Group
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

"""Widgets used in the Jupyter notebooks.

WARNING: AFTER EACH MODIFICATION, RESTART THE JUPYTER NOTEBOOK KERNEL !
"""

import inspect
import json
import os
import subprocess
import sys
from contextlib import chdir
from importlib import reload
from pathlib import Path
from runpy import run_path

import ipywidgets as widgets
import prefect
import rs_workflows
import yaml
from prefect.flows import Flow
from rs_common import prefect_utils
from rs_workflows.flow_utils import ProcessorEnum

#
# Jupyter doc: https://ipywidgets.readthedocs.io/en/latest/examples/Widget%20List.html
#

########################
# Choose DPR processor #
########################

dpr_proc_radio = widgets.RadioButtons(
    options=[(proc.name, proc) for proc in ProcessorEnum],
    value=ProcessorEnum.MOCKUP,
    description="DPR processor in this demo:",
    indent=False,
)

########################
# Deploy Prefect flows #
########################

# Deploy prefect flow from a YAML deployment file or using the S3 bucket ?
# The goal is to use the yaml file which itself should use the rs-client-libraries git repo and
# "develop" branch but it's hard to test changes in a new branch.
# So during development it's easier to deploy your local changes using a bucket.
deploy_prefect_radio = widgets.RadioButtons(
    options=[("YAML deployment file", "yaml"), ("S3 bucket", "bucket")],
    value="bucket",
    description="Deploy Prefect flows using:",
    indent=False,
)


async def deploy_prefect(
    deploy_file: str,
    s3_code_folder: str,
    work_pool_name: str,
) -> tuple[str] | str:
    """
    Deploy the Prefect flows that are implemented in the `rs-client-libraries` git repository.

    WARNING: the `rs-client-libraries` source code must be identical in these 3 environments:

    * https://github.com/RS-PYTHON/rs-demo.git (if we deploy using git)
    * This Jupyter environment
    * The Prefect Docker images

    Args:
        deploy_file: Prefect YAML deployment file path.
        s3_code_folder: S3 bucket folder where to deploy the source code.
        work_pool_name: prefect workpool name.

    Returns:
        Deployed flow name(s).
    """
    deployments = []
    deployed_names = []
    deploy_file = os.path.realpath(deploy_file)

    # Parent folder of the rs-client-libraries workflows
    rs_workflows_parent = Path(rs_workflows.__path__[0]).parent.absolute()

    print(f"Read Prefect YAML deployment file: {deploy_file!r}")
    with open(deploy_file, "r", encoding="utf-8") as opened:
        deploy_contents = yaml.safe_load(opened)

    # Read deployment info from yaml file
    for deployment in deploy_contents.get("deployments", []):
        try:
            name = deployment["name"]
            tags = deployment["tags"]
            entrypoint = deployment["entrypoint"]

            # The entrypoint should be something like <module_path>:<python_func>
            module, flow = entrypoint.split(":")

            # Read the entrypoint python module
            with chdir(rs_workflows_parent):
                flow_name = run_path(module)[flow].name

            # The deployed flow name is <flow_name>/<deployment_name>
            deployed_names.append(f"{flow_name}/{name}")

            # Save deployment info
            deployments.append((name, tags, entrypoint))

        except Exception as e:
            raise RuntimeError(
                f"Error reading deployment: {json.dumps(deployment, indent=2)}",
            ) from e

    # Deploy using the yaml file, from the rs_workflow parent folder
    if deploy_prefect_radio.value == "yaml":
        print(f"Deploy YAML file")
        cmd = [
            "prefect",
            "--no-prompt",
            "deploy",
            "--prefect-file",
            deploy_file,
            "--all",
        ]
        print(f"""cd {str(rs_workflows_parent)!r}; '{"' '".join(cmd)}'""")
        with chdir(rs_workflows_parent):
            subprocess.run(cmd)

    # Deploy using the S3 bucket
    else:
        # Use a specific secret block on the bucket for this subfolder
        code_bucket, _ = await prefect_utils.get_share_bucket(s3_code_folder)
        print(
            f"Deploy flows from S3 bucket folder: 's3://{code_bucket.bucket_name}/{code_bucket.bucket_folder}'",
        )

        # Upload workflows package contents
        await code_bucket.put_directory(
            local_path=rs_workflows.__path__[0],
            to_path="rs_workflows",
        )

        # Reload all rs-client-libraries modules
        for module in list(sys.modules.values()):
            if any(
                module.__name__.startswith(prefix)
                for prefix in ["rs_client.", "rs_common.", "rs_workflows."]
            ):
                reload(module)

        # Deploy the flows
        for deployment in deployments:
            name, tags, entrypoint = deployment
            flow = await prefect.flow.from_source(
                source=code_bucket,
                entrypoint=entrypoint,
            )
            await flow.deploy(
                name=name,
                work_pool_name=work_pool_name,  # note: we could try to read it from the yaml file instead
                tags=tags,
                ignore_warnings=True,
            )

    # Wait for deployments
    for deployed_name in deployed_names:
        await prefect_utils.wait_for_deployment(deployed_name)

    return deployed_names[0] if (len(deployed_names) == 1) else deployed_names


#####################
# Run Prefect flows #
#####################

# Run Prefect flows by either:
# - using the commande line (this is the regular usage)
# - calling directly the python code (faster and allows to debug with breakpoints)
run_prefect_radio = widgets.RadioButtons(
    options=[
        ["'prefect deployment run' command line", "cmd"],
        ["Pure python code", "python"],
        ["Only print arguments", "print"],
    ],
    value="cmd",
    description="Run Prefect flows using:",
    indent=False,
)


async def run_prefect(deploy_name: str, py_func: Flow, params: dict):
    """Run prefect flow"""

    deployment_url = f"{os.environ['RSPY_PREFECT_URL']}/deployments"
    print(
        f"Call {deploy_name!r} from {deployment_url} with:{json.dumps(params, indent=2)}",
    )

    if run_prefect_radio.value == "print":
        return

    # Using command line
    if run_prefect_radio.value == "cmd":
        cmd = [
            "prefect",
            "deployment",
            "run",
            deploy_name,
            "--params",
            json.dumps(params),
            "--watch",
        ]
        print(f"""Run from command line:\n'{"' '".join(cmd)}'""")
        subprocess.run(cmd)

    # By calling directly the python code
    else:
        print("Run from python code")
        # Reload all rs-client-libraries modules
        for module in list(sys.modules.values()):
            if any(
                module.__name__.startswith(prefix)
                for prefix in ["rs_client.", "rs_common.", "rs_workflows."]
            ):
                reload(module)

        # Make sure to call the python function from its reloaded module
        module = inspect.getmodule(py_func)
        py_func = getattr(module, py_func.fn.__name__)
        return await py_func(**params)


##########################
# Shutdown Dask clusters #
##########################

shutdown_checkbox = widgets.Checkbox(
    value=False,
    description="Shutdown the dask clusters",
    indent=False,
)
