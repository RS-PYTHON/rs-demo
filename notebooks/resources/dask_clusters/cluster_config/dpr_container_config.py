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

"""Extra configuration for the DPR scheduler and worker containers."""

import asyncio
import inspect
import json
import os
from concurrent.futures import ThreadPoolExecutor

var_name = "processing-storage-configuration"


def _get_prefect_values_from_env() -> dict:
    """
    Read the prefect payloads passed through the environment.
    This is the case when this file is imported inside a subprocess that is spawned by the 
    main Jupyter environment kernel (see dask_main_env.py in function _init_dask_cluster_main_env).
    """
    raw_values = os.getenv("DPR_CONTAINER_CONFIG_PREFECT_VALUES")
    if not raw_values:
        raise RuntimeError("DPR_CONTAINER_CONFIG_PREFECT_VALUES is not set")

    try:
        parsed_values = json.loads(raw_values)
    except Exception as exc:
        raise RuntimeError("DPR_CONTAINER_CONFIG_PREFECT_VALUES is not valid JSON") from exc

    if not isinstance(parsed_values, dict):
        raise RuntimeError("DPR_CONTAINER_CONFIG_PREFECT_VALUES must decode to a dictionary")

    return parsed_values


def _run_awaitable_sync(result):
    """Resolve an awaitable without re-entering a currently running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(result)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, result).result()


def _load_prefect_values_from_variable() -> dict:
    """Load values directly from the Prefect variable service."""
    try:
        from prefect.variables import Variable
    except ImportError as exc:
        raise RuntimeError("Prefect is required to resolve DPR container config values") from exc

    try:
        result = Variable.get(var_name)
    except Exception as exc:
        raise RuntimeError(
            f"Unable to load Prefect variable {var_name!r} and no environment payload was available",
        ) from exc

    if inspect.isawaitable(result):
        result = _run_awaitable_sync(result)

    if not isinstance(result, dict):
        raise RuntimeError(f"Prefect variable {var_name!r} must contain a dictionary")

    return result


def _get_prefect_values_sync() -> dict:
    """Load Prefect values from the environment first, then from the Prefect variable."""
    try:
        return _get_prefect_values_from_env()
    except RuntimeError:
        pass

    return _load_prefect_values_from_variable()


def extract_shared_disk_mounts(prefect_values: dict | None = None) -> list[dict]:
    """Extract shared-disk mounts from a storage_configuration payload."""
    values = prefect_values if prefect_values is not None else _get_prefect_values_sync()

    if not isinstance(values, dict):
        return []

    storage_configuration = values.get("storage_configuration")
    if not isinstance(storage_configuration, list):
        storage_configuration = values if isinstance(values, list) else []

    if not isinstance(storage_configuration, list):
        return []

    mounts = []
    for entry in storage_configuration:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") != "shared_disk":
            continue
        if not entry.get("name") or not entry.get("absolute_path"):
            continue

        mounts.append(
            {
                "name": str(entry["name"]),
                "mountPath": str(entry["absolute_path"]),
                "readOnly": False,
            },
        )

    return mounts


def resolve_dpr_container_config() -> dict:
    """Return the DPR container config with shared-disk mounts from Prefect."""
    prefect_values = _get_prefect_values_sync()
    shared_disk_mounts = extract_shared_disk_mounts(prefect_values)

    if shared_disk_mounts:
        return {"volumeMounts": shared_disk_mounts}

    return {"volumeMounts": []}


dpr_container_config = resolve_dpr_container_config()
print(f"[dpr_container_config] Resolved configuration: {dpr_container_config}")
