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

# The dask-gateway base image for local mode installs everything for the user "dask". It installs numpy v2.
# The L0 image installs everything for the user "root". It needs numpy v1.
# So it installs numpy v1 in the L0 image for the user "root".
# But when we do that, then we use the image from the user "dask", it will still use
# numpy v2 that has been installed for the user "dask".
# So here we uninstall the numpy version of the "dask" user. He will then use the root version.
# I don't know if there's a cleaner way to do this.
# NOTE: in cluster mode, the dask-gateway base image installs numpy v1.
if id dask >/dev/null 2>&1; then # if user "dask" exists
    su dask -c "pip uninstall -y numpy" # run "pip uninstall" for the "dask user
    su dask -c "python -c 'import numpy; print(numpy.__version__)'" # check that the "dask" user uses the root version
fi
