# rs-demo

[Jupyter](https://jupyter.org/) notebooks that showcase the features of [RS-Python](https://home.rs-python.eu/), the
Copernicus Reference System Python, and the **local mode** that runs the whole system on your computer with Docker
Compose.

## Overview

| Folder | Content |
|---|---|
| `notebooks/demos` | Demonstrations of the main use cases: search the stations, stage and process Sentinel-1 and Sentinel-3 products, inspect the generated products. |
| `notebooks/tutorials` | Tutorials, e.g. `prefect+dask` that shows how to run and deploy Prefect flows and use Dask from Jupyter. |
| `notebooks/init-prefect` | Notebooks used by the administrators to [initialise the processing environment](https://github.com/RS-PYTHON/rs-documentation/blob/develop/docs/administration/init-processing-environment.md): `env-vars` Prefect block, `processing-storage-configuration` Prefect variable. |
| `notebooks/init-dask-clusters` | Notebooks to [create the Dask clusters](https://github.com/RS-PYTHON/rs-workflow-env/blob/develop/docs/dask-clusters.md) of the staging and of the DPR processors. |
| `notebooks/processor-integration` | Notebook and configuration files used for the [integration of a new DPR processor](https://github.com/RS-PYTHON/rs-dpr-service/blob/develop/docs/doc/processor-integration.md). |
| `notebooks/sprints` | Demonstrations of the features delivered at each sprint. |
| `notebooks/z-integration` | Integration tests, run after the other notebooks. |
| `notebooks/resources` | Python helpers used by the notebooks, e.g. `init_demo()` that initialises your Prefect block, an `RsClient` instance and your object storage credentials. |
| `local-mode` | The [local mode](docs/local-mode.md): Docker Compose file and configuration. |
| `cluster-mode` | Script to run the notebooks on a cluster. |

## Getting started

### On a cluster

1. Log in to the JupyterHub of your platform, e.g. <https://processing.ops.rs-python.eu/jupyter> on the reference
   platform. You need an account on the platform and an [API key](https://github.com/RS-PYTHON/rs-documentation/blob/develop/docs/getting-started/user-rights.md#api-keys).
2. Open a terminal and clone this repository: `git clone https://github.com/RS-PYTHON/rs-demo.git`
3. Open a notebook of the `rs-demo/notebooks/demos` or `rs-demo/notebooks/tutorials` folders and run it. The first
   cells call `init_demo()`, that asks for your API key the first time and saves it in your `~/.env` file.

The [rs-client-libraries](https://github.com/RS-PYTHON/rs-client-libraries) are already installed in JupyterHub, see
[JupyterHub](https://github.com/RS-PYTHON/rs-documentation/blob/develop/docs/services/virtual-environment/jupyterhub.md)
to use another version.

### On your computer

Run the whole system with Docker Compose, see [Local mode](docs/local-mode.md):

```shell
cd local-mode
docker compose pull
docker compose down -v; docker compose up
```

## Documentation

- [Local mode](docs/local-mode.md)
- [Quickstart](https://github.com/RS-PYTHON/rs-documentation/blob/develop/docs/getting-started/quickstart.md) and
  [Create a custom flow](https://github.com/RS-PYTHON/rs-client-libraries/blob/develop/docs/doc/advanced/custom-flow.md)
- Online documentation of the whole project: <https://home.rs-python.eu/rs-documentation/>

## Related repositories

| Repository | Relationship |
|---|---|
| [rs-client-libraries](https://github.com/RS-PYTHON/rs-client-libraries) | The library and flows used by the notebooks. |
| [rs-server](https://github.com/RS-PYTHON/rs-server), [rs-dpr-service](https://github.com/RS-PYTHON/rs-dpr-service) | The services run by the local mode. Their CI tests their Docker images by running these notebooks. |
| [rs-testmeans](https://github.com/RS-PYTHON/rs-testmeans) | The mockups of the stations run by the local mode. |
| [rs-workflow-env](https://github.com/RS-PYTHON/rs-workflow-env) | The Jupyter and Dask images. |
| [rs-documentation](https://github.com/RS-PYTHON/rs-documentation) | Online documentation of the whole project. |

## Contributing

See the [contribution guidelines](https://github.com/RS-PYTHON/rs-documentation/blob/develop/docs/developers/contributing.md).
Report bugs in the [issue tracker](https://github.com/RS-PYTHON/rs-demo/issues). In case of sensitive bugs like
security vulnerabilities, please contact <ops_coprs@airbus.com> directly instead of using the issue tracker.

## Licensing

The code in this project is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).

---

![](https://raw.githubusercontent.com/RS-PYTHON/.github/refs/heads/main/profile/banner_logo.jpg)

This project is funded by the EU and ESA.
