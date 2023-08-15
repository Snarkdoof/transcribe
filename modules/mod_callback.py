import requests
import os
import shutil
import tempfile


ccmodule = {
    "description": "Callback over HTTP with urls to completed resources",
    "depends": [],
    "provides": [],
    "inputs": {
        "model": "Model used",
        "callbackurl": "URL to call back to (HTTP GET)",
        "weburl": "URL to the web server having the files",
        "webroot": "Directory to web server weburl",
        "contentid": "ID of content",
        "formatted": "The formatted VTT file",
        "vtt": "Original VTT (Whisper)",
        "text": "Text file",
        "json": "JSON file" 
    },
    "outputs": {
        "status": "ok",
        "vtt": "Final VTT url"
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


def process_task(cc, task):

    args = task["args"]

    # Copy the files to a new directory for publishing
    #dst = tempfile.mkdtemp(dir=args["webroot"])
    dst = os.path.join(args["webroot"], args["contentid"])
    if not os.path.exists(dst):
        os.makedirs(dst)
    os.chmod(dst, 0o775)
    webdst = args["weburl"]
    if webdst[-1] != "/":
        webdst+= "/"
    webdst += os.path.basename(dst) + "/"

    formatted = args["formatted"]
    vtt = args["vtt"]
    text = args["text"]
    json = args["json"]
    # copy files
    cc.log.info("Copying files to %s" % dst)
    for f in [formatted, vtt, text, json]:
        if os.path.abspath(f) != os.path.abspath(os.path.join(dst, f)):
            try:
                shutil.copy(f, dst)
            except:
                cc.log.exception("Error copying files")

    post = {
        "contentid": args["contentid"],
        "model": os.path.basename(args["model"]),
        "formatted": os.path.join(webdst, os.path.basename(formatted)),
        "vtt": os.path.join(webdst, os.path.basename(vtt)),
        "text": os.path.join(webdst, os.path.basename(text)),
        "json": os.path.join(webdst, os.path.basename(json)),
    }

    response = requests.get(args["callbackurl"], params=post)

    response.raise_for_status()

    return 100, {"status": "ok", "vtt": post["formatted"]}
