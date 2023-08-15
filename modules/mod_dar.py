import json
try:
    from libmediapipe.analyze import Analyzer
except Exception as e:
    import traceback
    traceback.print_exc()
    print("WARNING: Can't run DAR in this environment")

ccmodule = {
    "description": "Dyamic aspect ratio",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source video file",
        "dst": "Output file (aux), json format",
        "align_iframes": "Align to iframes, default false",
        "cast_file": "Output snaps of cast to this file if given (json), default None",
    },
    "outputs": {
        "dst": "Output file for AUX data",
        "cast": "Output file for cast (if requested)"
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


class Options:
    def __init__(self, align_iframes, cast):
        self.selfie = False
        self.tile = None
        self.iframes = align_iframes
        self.startts = 0
        self.endts = None
        self.cast = cast
        self.show = False

def process_task(cc, task):

    args = task["args"]
    src = args["src"]
    dst = args["dst"]
    align_iframes = args.get("align_iframes", False)
    cast_file = args.get("cast_file", None)

    if dst is None:
        # Not a video or no wish to process
        return 100, {"dst": None, "cast": None}

    options = Options(align_iframes, cast_file)
    analyzer = Analyzer(options)

    res = analyzer.analyze_video(src, options)

    # cv2.waitKey()  # <- Is this necessary to wait for it to complete?
    with open(dst, "w") as f:
        json.dump(res, f, indent=" ") 

    if cast_file:
        with open(cast_file, "w") as f:
            json.dump(analyzer.get_cast(), f, indent=" ")

    return 100, {"dst": dst, "cast": cast_file}
