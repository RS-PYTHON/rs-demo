from prefect import flow, task

@flow(name="s1_l0")
def staging():
    """
    Launch s1_l0 process
    """
    print("Launching s1_l0 flow ...")