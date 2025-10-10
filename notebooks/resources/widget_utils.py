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
from importlib import reload

import ipywidgets as widgets
from prefect.flows import Flow

##########################
# Shutdown Dask clusters #
##########################

shutdown_checkbox = widgets.Checkbox(
    value=False,
    description="Shutdown the dask clusters",
    indent=False,
)

########################
# Deploy Prefect flows #
########################

# Deploy flow from the rs-client-libraries git repo or using the bucket ?
# The goal is to use the git repo and "develop" branch but it causes errors
# when we make changes in a new branch.
deploy_prefect_radio = widgets.RadioButtons(
    options=[("Git repository ('develop' branch)", "git"), ("S3 bucket", "bucket")],
    value="bucket",
    description="Deploy Prefect flows using:",
    indent=False,
)

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
    ],
    value="cmd",
    description="Run Prefect flows using:",
    indent=False,
)


async def run_prefect(deploy_name: str, py_func: Flow, params: dict):
    """Run prefect flow"""

    sparams = "\n  - ".join([""] + [f"{key}: {value}" for key, value in params.items()])
    deployment_url = f"{os.environ['RSPY_PREFECT_URL']}/deployments"
    print(f"Call {deploy_name!r} from {deployment_url} with:{sparams}")

    # Using command line
    if run_prefect_radio.value == "cmd":
        subprocess.run(
            [
                "prefect",
                "deployment",
                "run",
                deploy_name,
                "--params",
                json.dumps(params),
                "--watch",
            ],
        )

    # By calling directly the python code
    else:
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
