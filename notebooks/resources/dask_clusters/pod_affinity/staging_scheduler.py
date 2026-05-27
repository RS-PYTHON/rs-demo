#!/opt/conda/envs/py3.13.12-2026.1.2/bin/python
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

"""Pod affinity for staging scheduler"""

staging_scheduler_affinity = {
    "affinity": {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": "node-role.kubernetes.io/access_csc",
                                "operator": "Exists",
                            },
                        ],
                    },
                ],
            },
        },
    },
    "tolerations": [
        {
            "key": "role",
            "operator": "Equal",
            "value": "access_csc",
            "effect": "NoSchedule",
        },
    ],
}
