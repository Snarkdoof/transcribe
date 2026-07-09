#!/usr/bin/env python3
import argparse
import json
import requests

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--url", required=True, help="URL value")
parser.add_argument("--weburl", required=True, help="Callback URL when done")
parser.add_argument("--contentid", required=True, help="ContentID value")
parser.add_argument("--lang", required=False, help="Language", default="no")
args = parser.parse_args()

# Create the JSON payload
data = {
    "url": args.url,
    "callbackurl": args.weburl,
    "contentid": args.contentid,
    "lang": args.lang
}

SERVER = "http://localhost:9993"

# Convert the payload to JSON
json_data = json.dumps(data)
print("POSTING", json_data)
# Send the POST request
response = requests.post(SERVER, json=data)

# Check the response status
response.raise_for_status()

job = response.json()
print(job)

# Loop and check the progress
while True:
    import time
    time.sleep(1)
    r = requests.get(SERVER + "/status/" + job["id"])
    if r.status_code != 200:
        raise SystemExit("Woops")
    status = r.json()
    for step in status["progress"]:
        state = step["done"]
        if step["progress"]:
            if step["progress"]["queued"]:
                state = "Waiting to start"
            if step["progress"]["allocated"]:
                state = "In progress"
            if step["progress"]["failed"]:
                state = "Failed"
        print("{:<25} {}".format(step["name"], state))
    print()

    if "retval" in status:
        print("Returned", status["retval"])
        break


