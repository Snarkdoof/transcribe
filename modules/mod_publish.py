
import os
import json
import shutil


ccmodule = {
    "description": "Publish the episode(s)",
    "depends": [],
    "provides": [],
    "inputs": {
        "episodes": "Episode information",
        "webroot": "What part of the destination is the web root (to be removed)",
        "dst": "Destination directory, will copy all manifests create episode.json in it",
        "copymedia": "Copy media files too, default false",
        "rsync": "What rsync statement to run if any (will be appended to 'rsync'"
    },
    "outputs": {
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


def process_task(cc, job):

    args = job["args"]

    episodes = args.get("episodes", [])
    webroot = args["webroot"]
    dst = args["dst"]
    copymedia = args.get("copymedia", False)
    rsync = args.get("rsync", None)

    if not os.path.exists(dst):
        os.makedirs(dst)

    for episode in episodes:
        path = os.path.join(dst, os.path.basename(episode["path"]))
        if episode["path"] != path:
            shutil.copy(episode["path"], path)
        del episode["path"]
        episode["manifest"] = path.replace(webroot, "")

        if copymedia:
            # should be a file for us to copy it!
            if not os.path.exists(episode["url"]):
                cc.log.error("Asked to copy media file '%s' but it isn't there" % episode["url"])
            else:
                if episode["url"] != dst:
                    shutil.copy(episode["url"], dst)

        # If URL is a file, replace webroot too
        if not episode["url"].startswith("http"):
            episode["url"] = episode["url"].replace(webroot, "")

    episodelist = os.path.join(dst, "episodes.json")
    with open(episodelist, "w") as f:
        json.dump(episodes, f, indent=" ")

    if rsync:
        import subprocess
        cc.log.info("Running rsync %s" % rsync)
        retval, output = subprocess.getstatusoutput("rsync " + rsync)
        if retval:
            cc.log.error("rsync returned %s" % retval)
            cc.log.error(output)
            raise Exception("rsync failed '%s': %s" % (rsync, output))
    return 100, {"dst": episodelist}
