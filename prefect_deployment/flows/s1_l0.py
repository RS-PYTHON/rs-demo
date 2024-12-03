from prefect import flow, task

@flow(name="s1_l0")
def staging():
    print("Launching s1_l0 flow ...")