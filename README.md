# rs-demo

## Run the demos

Prerequisites to run the demos locally using Jupyter Notebook: 

  * You have Docker installed on your system, see: https://docs.docker.com/engine/install/
  * You have access to the RSPY project on GitHub: https://github.com/RS-PYTHON
  * You have created a personnal access token (PAT) on GitHub: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens

To pull the latest Docker images, run:

```bash
# Login into the GitHub project Docker container (ghcr.io)
# Username: your GitHub login
# Password: your personnal access token (PAT) created above
docker login https://ghcr.io/v2/rs-python

# TODO document dind
# docker run --privileged --name my-dind-container -d -v /CHEMIN/VERS/TON/rs-demo/resources:/rs-demo/resources -p 8888:8888 docker:dind
# docker exec -it my-dind-container /bin/sh

# From the resources directory, pull the images
cd ./resources
docker compose pull
```

Then to run the demos:

```bash
# Still from the resources directory, if you're not there yet
cd ./resources

# Run all services:
docker compose up # -d for detached
```

You'll see in the logs e.g:
```
jupyter | To access the server, open this file in a browser:
jupyter |     ...
jupyter | Or copy and paste one of these URLs:
jupyter |     ...
jupyter |     http://127.0.0.1:8888/lab?token=612cb124335d9ab80a5a6414631a7df186b2401234050001
```

Open (ctrl-click) the http://127.0.0.1:8888/lab?token=... link to open the Jupyter web client (=Jupyter Notebook) in your browser.

On the left, in the file explorer, the demos are under /rspy-demos.

![alt text](./doc/images/jupyter.png "Title")

```bash
# When you're done, shutdown all services 
# with Ctrl-C (if not in detached mode i.e. -d) then:
docker compose down

# Remove docker named volumes
docker volume rm resources_rspy_working_dir resources_minio_storage
```

## How does it work

`docker compose`, implemented by the `rs-demo/resources/docker-compose.yml` file, uses Docker images to runs all the container services required by the demos :

  * The latest rs-server images available:
    * Built from the CI/CD: https://github.com/RS-PYTHON/rs-server/actions/workflows/publish-binaries.yml
    * Available in the Docker container: https://github.com/orgs/RS-PYTHON/packages
  * The CADIP, ADGS, ... station mockups
  * STAC PostgreSQL database
  * MinIO S3 bucket server
  * Jupyter server

The Jupyter notebooks accessed from http://127.0.0.1:8888 are run from the containerized Jupyter server, not from your local computer. 
The server contains the necessary Python modules to call the rs-server HTTP endpoints.

## [TIP] to run your local rs-server code in this environment

It can be helpful to use your last rs-server code version to debug it or to test modifications without pushing them and rebuilding the Docker image.

If your local github repository is under `/my/local/rs-server`, modify the `rs-demo/resources/docker-compose.yml` file to mount your volumes file into the `rs-server` service. Use absolute paths. Don't commit this modification !
```yaml
volumes:
  - /my/local/rs-server/rs_server:/usr/local/lib/python3.11/site-packages/rs_server
  - /my/local/rs-server/services/common/rs_server_common:/usr/local/lib/python3.11/site-packages/rs_server_common
  - /my/local/rs-server/services/cadip/rs_server_cadip:/usr/local/lib/python3.11/site-packages/rs_server_cadip
  - and other config files ...
```