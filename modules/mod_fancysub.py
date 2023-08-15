import json
import random
import os

ccmodule = {
    "description": "Transform CSV to Fancysub",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source file to convert, CSV",
        "dst": "Destination file",
        "baseurl": "Base url for resources, used for manifest",
        "baseid": "The ID of this pice of content (appended to baseurl), default ''",
        "mediaurl": "URL for media, used for manifest"
    },
    "outputs": {
        "dst": "Output fancusub file",
        "cast": "Output cast file",
        "manifest": "Output manifest file"

    },
    "defaults": {
        "priority": 50,  # Normal
        "runOn": "success"
    },
    "status": {
        "progress": "Progress 0-100%",
        "state": "Current state of processing"
    }
}


def new_speaker(id):
    def r():
        return random.randint(0, 180)
    color = '#%02X%02X%02X' % (r(), r(), r())

    return {
        "name": id,
        "color": color,
        "src": ""
    }


def cleanup_text(text):
    """
    Remove "eee" thinking breaks and replace qqq with laughter icon.
    """
    import re

    # We might get lots of spaces we don't want
    for i, r in [("q q", "qq"), ("e e e", "eee"), ("m m m", "mmm")]:
        text = re.sub(i, r, text, flags=re.I)
        text = re.sub(i, r, text, flags=re.I)  # I gave up properly doing regex

    for e, url in [
        ("qq+", "https://wp4.demos.mediafutures.no/res/emotions/laugh.png"),
        ("mmm", "https://wp4.demos.mediafutures.no/res/emotions/think.png")
      ]:
        emotion = " <img class='emoticon' src='%s'/> " % url
        text = re.sub(e, emotion, text, flags=re.I)

    text = re.sub("ee+ ?", "", text, flags=re.I)
    return text.strip()


def process_task(cc, task, stop_event):

    args = task["args"]

    if not args["dst"].endswith(".json"):
        args["dst"] += ".json"

    cast_file = os.path.splitext(args["dst"])[0] + "_cast.json"
    subs_file = os.path.splitext(args["dst"])[0] + "_subs.json"
    manifest_file = args["dst"]

    cc.log.debug("Processing %s" % str(args["src"]))

    cast = {}
    subs = []

    with open(args["src"], "r") as f:
        for line in f.readlines():
            if not line.strip():
                continue
            speaker, start, end, duration, fn, text = line.split(",", 5)

            if not start.replace(".", "").isnumeric():
                continue  # Bad line

            if speaker not in cast:
                cast[speaker] = new_speaker(speaker)

            text = cleanup_text(text)
            if text == "":
                continue

            sub = {
                "start": float(start),
                "end": float(end),
                "text": text,
                "who": speaker
            }
            subs.append(sub)

    # Write to files
    with open(subs_file, "w") as f:
        json.dump(subs, f, indent=" ")

    with open(cast_file, "w") as f:
        json.dump(cast, f, indent=" ")

    print("Baseurl", args.get("baseurl"), "subs", subs_file)
    baseurl = args.get("baseurl", ".")
    baseid = args.get("baseid", "")
    if baseid:
        baseurl += "/" + baseid
    manifest = {
        "id": random.randint(0, 4000000),
        "subtitles": [{"src": os.path.join(baseurl, os.path.basename(subs_file))}],
        "cast": os.path.join(baseurl, os.path.basename(cast_file))
        }

    if args.get("mediaurl", None):
        if args["mediaurl"].startswith("http"):
            mediaurl = args["mediaurl"]
        else:
            mediaurl = os.path.join(baseurl, os.path.basename(args["mediaurl"]))

        if args["mediaurl"].endswith(".mp3"):
            manifest["audio"] = {"src": mediaurl}
        else:
            manifest["video"] = {"src": mediaurl}

    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=" ")

    return 100, {"result": "ok", "dst": subs_file, "cast": cast_file, "manifest": manifest_file}
