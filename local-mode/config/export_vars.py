#!/usr/bin/env python3

import sys
import yaml
import os

PREFIX = "RSPY__TOKEN__"

def to_env_key(*parts):
    return PREFIX + "__".join(part.upper() for part in parts)

def write_env_file(env_vars, path=".env2"):
    with open(path, "w", encoding="utf-8") as f:
        for key, value in env_vars.items():
            if value:
                f.write(f"{key}={value}\n")

def main():
    if len(sys.argv) != 2:
        print("Usage: generate_env_from_yaml.py <yaml_file>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    data_sources = config.get("external_data_sources", {})
    env_vars = {}

    for station_key, station_data in data_sources.items():

        station = station_key.upper()

        service_name = station_data.get("service", {}).get("name")
        if not service_name:
            print(f"Missing service.name for {station_key}", file=sys.stderr)
            continue

        service = service_name.upper()

        for key, value in station_data.get("service", {}).items():
            env_key = to_env_key(service, station, "SERVICE", key)
            env_vars[env_key] = value

        for key, value in station_data.get("authentication", {}).items():
            parts = key.split("_")
            env_key = to_env_key(service, station, "AUTHENTICATION", *parts)
            env_vars[env_key] = value

        if "domain" in station_data:
            env_key = to_env_key(service, station, "DOMAIN", "VALUE")
            env_vars[env_key] = station_data["domain"]

        trusted = station_data.get("trusteddomains", [])
        if trusted:
            value = "[" + ", ".join(trusted) + "]"
            env_key = to_env_key(service, station, "TRUSTEDDOMAINS")
            env_vars[env_key] = value
        
    write_env_file(env_vars)

if __name__ == "__main__":
    main()