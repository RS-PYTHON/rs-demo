#!/bin/sh

# Copyright 2026 Airbus, CS Group
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

set -eu

S3CFG_PATH="${S3CFG_PATH:-/.s3cfg}"

if [ ! -r "$S3CFG_PATH" ]; then
    >&2 echo "Missing readable S3 config file: '$S3CFG_PATH'"
    exit 1
fi

read_s3cfg() {
    key="$1"
    awk -F '=' -v key="$key" '
        $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
            value = $2
            sub(/^[[:space:]]+/, "", value)
            sub(/[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$S3CFG_PATH"
}

export S3_ACCESSKEY="$(read_s3cfg access_key)"
export S3_SECRETKEY="$(read_s3cfg secret_key)"
export S3_ENDPOINT="$(read_s3cfg host_bucket)"
export S3_REGION="$(read_s3cfg bucket_location)"

if [ -z "$S3_ACCESSKEY" ] || [ -z "$S3_SECRETKEY" ] || [ -z "$S3_ENDPOINT" ] || [ -z "$S3_REGION" ]; then
    >&2 echo "Missing S3 values in '$S3CFG_PATH'. Expected access_key, secret_key, host_bucket, bucket_location."
    exit 1
fi

if [ "$#" -eq 0 ]; then
    >&2 echo "No startup command provided to prepare_s3_env_from_s3cfg.sh"
    exit 1
fi

exec "$@"
