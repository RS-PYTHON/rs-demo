#!/opt/conda/bin/python
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

"""
This module is a command-line application, always run from the main Jupyter env (see the first line of this module:
#!/opt/conda/bin/python) that is used by the sub-venvs/kernels (that do not have prefect) to read the
# JUPYTERHUB_API_TOKEN from the Prefect block.
"""

from prefect.blocks.system import Secret

# Prefect block names
BLOCK_NAME_ENV_GLOBAL: str = "env-vars"

token = Secret.load(BLOCK_NAME_ENV_GLOBAL).get()["JUPYTERHUB_API_TOKEN"]

print(token)
