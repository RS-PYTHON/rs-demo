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

try:
    from prefect.variables import Variable
except ImportError:
    Variable = None

async def get_prefect_variable_values() -> dict:
    """Read the Prefect variable that stores the storage configuration."""
    var_name = "processing-storage-configuration"
    
    try:
        existing_values = await Variable.get(var_name)            
    except AttributeError as exc:
        raise RuntimeError(
            f"Prefect variable {var_name!r} is missing or unreadable",
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Prefect variable {var_name!r} is missing or unreadable",
        ) from exc    

    if isinstance(existing_values, dict):
        return existing_values

    raise RuntimeError(f"Prefect variable {var_name!r} must contain a dictionary")


def extract_shared_disk_mounts(prefect_values: dict | None = None) -> list[dict]:
    """Extract shared-disk mounts from a storage_configuration payload."""
    values = prefect_values if prefect_values is not None else asyncio.run(get_prefect_variable_values())

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
    prefect_values = asyncio.run(get_prefect_variable_values())
    shared_disk_mounts = extract_shared_disk_mounts(prefect_values)

    if shared_disk_mounts:
        return {"volumeMounts": shared_disk_mounts}

    return {"volumeMounts": []}


dpr_container_config = resolve_dpr_container_config()
