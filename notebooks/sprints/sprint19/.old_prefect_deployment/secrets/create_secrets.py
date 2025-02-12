""" This module creates prefect secrets as blocks.
These secrets may be accessed later in a prefect configuration deployment yaml file,
with the following format (example, setting an env var)
...
deployments:
- name: example_deployment
    .....
    work_pool:
    name: example-pool
    job_variables:
      env:
        EXAMPLE_ENV_VAR: "{{ prefect.blocks.secret.name }}"

where name from prefect.blocks.secret.name is going to be set with the corresponding value
from the user's input for this script, in a form of a list with this
format: [(value1, name1), (value2, name2), ...]
"""

import argparse
import ast
import re

from prefect.blocks.system import Secret


def main():
    """Create prefects blocks secrets"""
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Create Prefect secrets from a list of value-name pairs.",
    )
    parser.add_argument(
        "pairs",
        type=str,
        help="List of (value, name) pairs in the format: [(value1, name1), (value2, name2), ...]. "
        "Pay attention at the format of the name, that must only "
        "contain lowercase letters, numbers, and dashes. Example: "
        'python create_secrets.py \'[("value-test-1", "name-test-1"), ("value-test-2", "name-test-2")]\'',
    )

    # Parse arguments
    args = parser.parse_args()

    # Convert the input string to a list of tuples
    try:
        pairs = ast.literal_eval(args.pairs)
        if not isinstance(pairs, list) or not all(
            isinstance(pair, tuple) and len(pair) == 2 for pair in pairs
        ):
            raise ValueError("Input must be a list of (value, name) pairs.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Invalid input format: {e}")
        return

    # Create secrets
    name_pattern = re.compile(r"^[a-z0-9\-]+$")  # Pattern for valid names
    for value, name in pairs:
        if not name_pattern.match(name):
            print(
                f"Invalid name '{name}': must contain only lowercase letters, numbers, and dashes.",
            )
            continue  # Skip invalid name

        try:
            Secret(value=value).save(name=name, overwrite=True)
            print(f"Secret saved successfully: {name}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Failed to save secret '{name}': {e}")


if __name__ == "__main__":
    main()
