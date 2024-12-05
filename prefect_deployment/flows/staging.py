from prefect import flow, task

@flow(name="staging")
def staging():
    """
    Launch staging process
    """
    # staging.run_staging()
    print("Launch staging flow...")


#if __name__ == "__main__":
    # Creates a deployment from your flow and immediately begins listening for scheduled runs to execute
    # staging.serve(name="my-first-deployment", cron="* * * * *")

    # Create a deployment: here’s an example of a deployment that uses a work pool and bakes the code into a Docker image
    # staging.deploy(
    #     name="my-second-deployment",
    #     work_pool_name="my-work-pool",
    #     image="my-image",
    #     push=False,
    #     cron="* * * * *",
    # )