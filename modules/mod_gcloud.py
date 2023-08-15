import subprocess
import time


ccmodule = {
    "description": "Reformat subs based on whisper_timestamp with timestamped words",
    "depends": [],
    "provides": [],
    "inputs": {
        "start": "List of instances to ensure are running (or comma separated string)",
        "stop": "List of instances to ensure are running (or comma separated string)",
        "stopifidle": "Only stop if idle, default True",
        "timeout": "Of stopifidle, allow waiting up to this many seconds for things to stop before giving up"
    },
    "outputs": {
        "result": "ok (exception if not)"
    },
    "defaults": {
        "priority": 50,  # Normal        "runOn": "success"
        "type": "admin"
    },
    "status": {
        "progress": "Progress 0-100%",
        "state": "Current state of processing"
    }
}



def list_instances():
    """
    Keys are: NAME, ZONE, MACHINE_TYPE, PREEMPTIBLE, INTERNAL_IP, EXTERNAL_IP, STATUS
    """ 
    # Run the command and capture the output
    command = 'gcloud compute instances list'
    output = subprocess.check_output(command, shell=True, text=True)


    # Split the output into separate rows
    rows = output.strip().split('\n')

    # Extract the column start points from the title line
    title_line = rows[0]
    column_starts = [title_line.index(field) for field in title_line.split()]

    # Parse the rest of the rows as dictionaries
    data = []
    for row in rows[1:]:
        values = [row[column_starts[i]:column_starts[i+1]].strip() for i in range(len(column_starts) - 1)]
        values.append(row[column_starts[-1]:].strip())
        data.append(dict(zip(title_line.split(), values)))

    return data

def get_instance(name):
    instances = list_instances()
    for instance in instances:
        if instance["NAME"] == name:
            return instance

    raise Exception("Unknown instance {}".format(name))


def start_if_stopped(cc, name):

    instance = get_instance(name)
    print("Got instance", instance)
    if instance["STATUS"] == "RUNNING":
        return False

    # Start it
    cc.log.info("Starting instance {}".format(name))
    cmd = "gcloud compute instances start {} --zone={}".format(instance["NAME"], instance["ZONE"])
    output = subprocess.check_output(cmd, shell=True, text=True)

    # Check output
    return True

def stop_if_running(cc, name, stopifidle, timeout=10, minuptime=600):
    """
    If stopifidle is given, we wait for up to the given timeout and see if it stops
    """

    if stopifidle:
        idle = True
        endtime = time.time() + timeout
        while time.time() < endtime:
            # Check that we're idle first!
            if subprocess.call("ccisidle", shell=True) == 0:
                break
            else:
                idle = False
                time.sleep(1)
        if not idle:
            cc.log.info("Not stopping instance {}, not idle".format(name))
            return False

    if minuptime and minuptime > get_uptime():
        cc.log.warning("Asked to turn off but minimum uptime has not passed")
        return False

    instance = get_instance(name)
    print("Got instance", instance)
    if instance["STATUS"] != "RUNNING":
        return False

    # Stop it
    cc.log.info("Stopping instance {}".format(name))
    cmd = "gcloud compute instances stop {} --zone={} --discard-local-ssd=false".format(instance["NAME"], instance["ZONE"])
    output = subprocess.check_output(cmd, shell=True, text=True)

    # Check output
    return True


def get_uptime():
    import psutil
    import datetime

    # Get the system boot time
    boot_time = psutil.boot_time()

    # Calculate the current uptime
    uptime_seconds = int(datetime.datetime.now().timestamp() - boot_time)
    return uptime_seconds

def process_task(cc, task):
    """
    Check that the given instance(s) are running
    """
    num_running = 0
    num_started = 0
    num_stopped = 0

    args = task["args"]
    start = args.get("start", None)
    stopifidle = args.get("stopifidle", True)
    timeout = args.get("timeout", 10.0)
    minuptime = args.get("minuptime", 300)

    if start:
        if not isinstance(start, list):
            start = start.split(",")
        for name in start:
            if start_if_stopped(cc, name):
                num_started += 1
            else:
                num_running += 1

    stop = task["args"].get("stop", None)
    if stop:
        if not isinstance(stop, list):
            stop = stop.split(",")
        for name in stop:
            if stop_if_running(cc, name, stopifidle, timeout, minuptime):
                num_stopped += 1


    return 100, {"result": "ok", "started": num_started, "running": num_running, "stopped": num_stopped}
