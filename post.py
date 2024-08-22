#!/usr/bin/env python3
import argparse
import json
import requests

import curses
import time

default_models = {
    "no": "NbAiLab/nb-whisper-large",
    "en": "large-v2"
}


def get_states(jobs):
    """
    Get updates for all given jobs
    """

    # request is a list of job id's
    request = [job['id'] for job in jobs]
    r = requests.post(SERVER + "/status/", json=request)
    print(r)
    if r.status_code != 200:
        raise SystemExit("Woops")
    status = r.json()
    return status


def update_screen(stdscr, jobs, state):
    """
    jobs: [{"id": jobid, resourceid": ..., "url": ...}]
    state: {"resourceid": job's id, "retval": any return value,
            "steps": {"name": ..., "state":...} }
    """
    if stdscr:
        stdscr.clear()
        stdscr.addstr(0, 0, "Jobs:\n")

    with open("/tmp/dbg", "w") as f:
        f.write("STATE: " + json.dumps(state) + "\n")
        f.write("jobs: " + json.dumps(jobs) + "\n")

    offset = 1
    for i, job in enumerate(jobs, start=1):

        if not stdscr:
            print(f"job: {job['id']}, {job['url']}")
        # Check job state status
        if job["id"] in state:
            s = state[job["id"]]

            # Not done, how long are we?
            for step in s["steps"]:
                if "retval" in s:
                    if stdscr:
                        if "status" in s['retval']:
                            txt = s['retval']['status']
                        else:
                            txt = s['retval']
                        stdscr.addstr(offset, 0, f"{job['id']}   Done  {txt}\n")
                        offset += 1
                    else:
                        print("   Done\n")
                        print(f"     {s['retval']}\n")
                    break
                elif step["state"] != "Done":
                    # This is the one we show
                    if stdscr:
                        stdscr.addstr(offset, 0, f"{job['id']}   {step['name']} {step['state']}\n")
                        offset += 1
                    else:
                        print(f"   {step['name']} {step['state']}\n")

                    break
    if stdscr:
        stdscr.refresh()


# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--url", required=False, help="URL value", default="")
parser.add_argument("--weburl", required=False, help="Callback URL when done", default="")
parser.add_argument("--contentid", required=True, help="ContentID value")
parser.add_argument("--lang", required=False, help="Language", default="no")
parser.add_argument("--model", required=False, help="Model", default="")
parser.add_argument("--reprocess", action="store_true",
                    help="Specify whether to reprocess or not", default=False)
parser.add_argument("--resources", required=False, default=None,
                    help="Filename with list of resources, id: url\n")
parser.add_argument("--curses", required=False, action="store_true", help="Model", default=False)

args = parser.parse_args()

if not args.resources:
    if not args.url and not args.contentid:
        raise SystemExit("Need either resource or url and contentid")

# Create the JSON payload
data = {
    "url": args.url,
    "callbackurl": args.weburl,
    "contentid": args.contentid,
    "lang": args.lang,
    "reprocess": args.reprocess,
}
if args.model:
    data["model"] = args.model
else:
    data["model"] = default_models[args.lang]

# SERVER = "https://cc.nlive.no/transcribe"
# SERVER = "https://autotext.elevkanalen.no/transcribe"
SERVER = "http://localhost:9996/"

if args.resources:
    with open(args.resources, "r") as f:
        resources = [line.split(":", 1) for line in f.readlines()]
else:
    resources = [[args.contentid, args.url]]

resources = [{"id": r[0], "url": r[1].strip()} for r in resources][:5]

jobs = []

for resource in resources:
    data["url"] = resource["url"]
    data["contentid"] = resource["id"]

    # Convert the payload to JSON
    json_data = json.dumps(data)
    print("POSTING", json_data)
    # Send the POST request
    response = requests.post(SERVER, json=data)
    # Check the response status
    response.raise_for_status()

    job = response.json()
    job["resourceid"] = resource["id"]
    job["url"] = resource["url"]
    jobs.append(job)
    print("   ", job["id"])

# Loop and check the progress
last_s = {}
return_values = []


def main(stdscr):
    # Clear screen
    if stdscr:
        stdscr.clear()

    import copy
    activejobs = copy.copy(jobs)

    state = {}
    return_values = []
    while True:
        f = open("/tmp/dbg2", "w")
        jobs_left = 0
        try:
            multistate = get_states(activejobs)
        except Exception:
            time.sleep(5)
            continue

        for job in jobs:
            if job["id"] not in state:
                state[job["id"]] = {"resourceid": job["resourceid"], "steps": {}}

            if "retval" in state[job["id"]]:
                continue
            jobs_left += 1

            status = multistate[job['id']]
            steps = []
            if "progress" not in status:
                continue

            for step in status["progress"]:
                s = step["done"]
                if step["progress"]:
                    if step["progress"]["queued"]:
                        s = "Waiting to start"
                    if step["progress"]["allocated"]:
                        s = "In progress"
                    if step["progress"]["failed"]:
                        s = "Failed"
                steps.append({"name": step["name"], "state": s})
                # if step["name"] not in state[job["id"]]["steps"]:
                #    state[job["id"]]["steps"][step["name"]] = s
                # state[job["id"]]["steps"][step["name"]] = s
            state[job["id"]]["steps"] = steps

            if "retval" in status:
                state[job["id"]]["retval"] = status["retval"]
                for j in activejobs:
                    if j["id"] == job["id"]:
                        activejobs.remove(j)
                        break
                return_values.append(status)
            try:
                update_screen(stdscr, jobs, state)
            except Exception:
                pass

        if len(activejobs) == 0:
            with open("/tmp/return_values.json", "w") as f:
                json.dump(return_values, f, indent=2)
            break

        f.close()
        try:
            update_screen(stdscr, jobs, state)
        except Exception:
            pass
        time.sleep(5)

    # Wait for escape to exit
    while stdscr:
        # stdscr.nodelay(True)
        key = stdscr.getch()
        if key == 27:
            break
        # Refresh the screen
        stdscr.refresh()


if __name__ == "__main__":

    print("Starting curses")
    # If we're using curses
    if args.curses:
        curses.wrapper(main)
    else:
        main(None)
    print("CURSES RUNNING")
