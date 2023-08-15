import os.path
import requests


ccmodule = {
    "description": "Prepare transcript",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source file to transcribe",
        "dir": "Temporary directory",
        "dst": "Destionation file",
        "item": "Item map containing keys 'id', 'url' and 'processed'",
        "baseurl": "Base URL for final files"
    },
    "outputs": {
        "src": "Source file (might be downloaded)",
        "dst": "Output file",
        "videofile": "Video file (or None if not video)",
        "wavfile": "Temporary sound file",
        "wavfilemono": "Temporary mono sound file",
        "mp3file": "Output file for distribution",
        "subfile": "Temporary sub file if necessary",
        "auxfile": "Output file for DAR",
        "manifest": "Manifest file",
        "baseurl": "Modified base URL for this resource",
        "infofile": "Info cards",
        "basename": "The basename of the file (for output files)"
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


def download(url, destination):

    if os.path.exists(destination):
        return destination

    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(destination, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return destination


def process_task(cc, task):

    args = task["args"]
    tmpdir = args.get("dir", "/tmp")

    if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)

    if args.get("item", None):
        # We got an item to download, with keys id and url (and "processed")
        # If already processed, don't process it
        args["src"] = os.path.join(tmpdir, os.path.basename(args["item"]["url"]))
        defpath = os.path.join(os.path.dirname(args["item"]["path"]), args["item"]["id"])
        args["dst"] = args["item"].get("path", defpath)
        url = args["item"]["url"]
        if not args["item"].get("processed", False):
            print("DOWNLOAD", url, "->", args["src"])
            cc.log.info("Downloading '%s'" % args["src"])
            download(url, args["src"])
    else:
        cc.log.info("SRC '%s'" % str(args["src"]))
        if args["src"].startswith("http") and not args["src"].count("m3u8") > 0:
            url = args["src"]
            args["src"] = os.path.join(tmpdir, os.path.basename(url))
            cc.log.info("Downloading '%s'" % args["src"])
            download(url, args["src"])
            cc.log.debug("Downloaded OK")

    basename = os.path.basename(os.path.splitext(args["src"])[0])
    wav = os.path.splitext(args["src"])[0] + ".wav"
    wav = os.path.join(tmpdir, os.path.basename(wav))

    wavmono = os.path.splitext(args["src"])[0] + "_mono.wav"
    wavmono = os.path.join(tmpdir, os.path.basename(wavmono))

    d = args["dst"]
    if d.endswith("/"):
        d += os.path.splitext(os.path.basename(args["src"]))[0]
    else:
        d = os.path.splitext(args["dst"])[0]
    mp3 =  d + ".mp3"
    subs = d + "_subs.json"
    info = d + "_info.json"
    manifest = d + ".json"

    # if not os.path.splitext(args["dst"])[1]:
        # Target is a directory, create a manifest name that is sensible
    #    args["dst"] = os.path.join(d, os.path.basename(os.path.splitext(args["src"])[0]) + ".json")
    
    p = os.path.split(args["dst"])[0]
    if not os.path.exists(p):
        os.makedirs(p)

    # If this is a video, we also provide the AUX file for Dynamic Aspect Ratio (DAR)
    if os.path.splitext(args["src"].lower())[1] in [".mp4", ".webm", ".avi"]:
        auxfile = d + "_aux.json"
        videofile = d + os.path.splitext(args["src"].lower())[1]
        cc.log.debug("Target VIDEO file is '%s'" % videofile)
        if not os.path.exists(videofile):
            # COPY
            cc.log.info("Copying video file to '%s" % videofile)
            import shutil
            shutil.copy(args["src"], videofile)
    else:
        auxfile = None
        videofile = None

    cc.log.debug("Prepare is OK")

    return 100, {"result": "ok", "src": args["src"], "wavfile": wav, "manifest": manifest,
                 "mp3file": mp3, "subfile": subs, "wavfilemono": wavmono, "dst": p,
                 "infofile": info, "auxfile": auxfile, "videofile": videofile, "basename": basename}
