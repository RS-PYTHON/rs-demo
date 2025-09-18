#!/usr/bin/env bash
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

set -euo pipefail
set -x

# The dask-gateway base image for local mode installs numpy v2 for user "dask".
# This is incompatible with L0 which requires numpy v1.
# But even with forcing numpy v1 in the root install, the "dask" user still uses his numpy v2.
# So here we uninstall the numpy version of the "dask" user. He will use the root version.
# I don't know if there's a cleaner way to do this.
# NOTE: in cluster mode, the dask-gateway base image installs numpy v1.
if id dask >/dev/null 2>&1; then # if user "dask" exists
    su dask -c "pip uninstall -y numpy" # run "pip uninstall" for the "dask user
    su dask -c "python -c 'import numpy; print(numpy.__version__)'" # check that the "dask" user uses the root version
fi
