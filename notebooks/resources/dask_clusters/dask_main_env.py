# Copyright 2023-2026 Airbus, CS Group
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

"""Init dask clusters from the main Jupyter environment kernel."""

import asyncio
import os
import subprocess
from pathlib import Path

from IPython import get_ipython
from resources import utils
from resources.dask_clusters import dask_utils
from resources.dask_clusters.dask_utils import local_mode
from rs_client.ogcapi.dpr_client import ClusterInfo

NOTEBOOK_DIR = Path(__file__) / "../../../init-dask-clusters"

##########################
# Global implementations #
##########################


async def _init_dask_cluster_main_env(notebook_path: Path) -> ClusterInfo:
    """
    From the main Jupyter environment kernel, we call a notebook (in command line) that will
    read an existing or create a new dask cluster.
    """
    notebook_path = notebook_path.resolve()

    # Use papermill to call the notebook in a subprocess.
    # It will use the venv kernel that is defined in the notebook.
    cmd = [
        "papermill",
        str(notebook_path),
        "/tmp/out.ipynb",
        "--log-output",
    ]
    print(f"Run command line:\n{' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Read papermill output line by line
    while proc.stdout:
        line = (await proc.stdout.readline()).decode("utf-8")
        if not line:  # process has finished
            break

        # Print line if not empty
        if line := line.rstrip():
            print(line)

        # The notebook will hit this line after it has finished initializing the dask cluster
        if dask_utils.KEEP_THIS_NOTEBOOK_OPEN in line:
            break

    if proc.returncode not in [None, 0]:
        print("=== AN ERROR OCCURRED ===")
        raise RuntimeError(f"Error initializing dask cluster")

    # NOTE: we don't want to kill the subprocess, we need to keep it alive.
    # It will be killed when you restart your Jupyter kernel.

    # Read ClusterInfo value as a IPython variable
    # NOTE: this is not thread-safe, maybe we should use a more specific variable name.
    ipython = get_ipython()
    _cluster_info = ipython.db["cluster_info"]
    cluster_info = ClusterInfo(**_cluster_info)

    # Set environment to run static payload (=job order) files.
    # In local mode, the dask gateway address is different for each eopf cluster (l0, l1, ...)
    # We need this address in some config files. So we update this env var from the current cluster value.
    # NOTE: this is not thread-safe, these variables will be overridden if we init several clusters from the same demo.
    if local_mode:
        os.environ["DASK_GATEWAY_ADDRESS"] = os.environ[
            ipython.db["local_mode_address"]
        ]
        os.environ["DASK_GATEWAY_PUBLIC"] = os.environ[
            ipython.db["local_mode_address_public"]
        ]
        os.environ["DASK_CLUSTER_INSTANCE"] = cluster_info.cluster_instance
        # Refresh Prefect blocks to pass these env vars to the dask workers
        utils.init_prefect_blocks(_sync=True)

    return cluster_info


###############################
# Init each dask cluster type #
###############################


async def init_dask_cluster_cpm2():
    """Read existing or create new dask cluster."""
    return await _init_dask_cluster_main_env(
        NOTEBOOK_DIR / "init_dask_cluster_cpm2.ipynb",
    )


async def init_dask_cluster_cpm3():
    """Read existing or create new dask cluster."""
    return await _init_dask_cluster_main_env(
        NOTEBOOK_DIR / "init_dask_cluster_cpm3.ipynb",
    )


async def init_dask_cluster_eopf_mockup():
    """Read existing or create new dask cluster."""
    return await _init_dask_cluster_main_env(
        NOTEBOOK_DIR / "init_dask_cluster_eopf_mockup.ipynb",
    )


async def init_dask_cluster_l0():
    """Read existing or create new dask cluster."""
    return await _init_dask_cluster_main_env(
        NOTEBOOK_DIR / "init_dask_cluster_l0.ipynb",
    )


async def init_dask_cluster_s1ard():
    """Read existing or create new dask cluster."""
    return await _init_dask_cluster_main_env(
        NOTEBOOK_DIR / "init_dask_cluster_s1ard.ipynb",
    )


async def init_dask_cluster_s3olci():
    """Read existing or create new dask cluster."""
    return await _init_dask_cluster_main_env(
        NOTEBOOK_DIR / "init_dask_cluster_s3olci.ipynb",
    )


async def init_dask_cluster_staging():
    """Read existing or create new dask cluster."""
    return await _init_dask_cluster_main_env(
        NOTEBOOK_DIR / "init_dask_cluster_staging.ipynb",
    )
