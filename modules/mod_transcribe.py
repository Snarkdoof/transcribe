import subprocess
import fcntl
import os
import select


ccmodule = {
    "description": "Transcribe a WAV file",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source file to transcribe",
        "mode": "'diarize', 'transcribe', 'background', 'convert'",
        "dst": "Destination file",
        "model": "The model to use, default is 'NbAiLab/nb-wav2vec2-1b-bokmaal'",
        "format": "Specify the file format of a transcription file.Possible options are csv, " +
                  "eaf or srt. Defaults to csv.The eaf and srt options are only implemented " +
                  "for the 'transcribe' and 'convert' modes.If no format is specified in 'convert' " +
                  "mode, an eaf file isproduced",
        "dir": "Where to find w2vtranscriber",
        "segments": "CSV file with segments to use (if not given, segments are detected)",
        "lang": "If no model is given, it uses either facebook or NbAiLab. Supported 'no', 'en'"
    },
    "outputs": {
        "dst": "Output file"

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


def process_task(cc, task, stop_event):

    print("MOD_TRANSCRIBE", task)
    print(os.environ["PYTHONPATH"])

    cmd = ["python3", "-m", "w2vtranscriber.transcription_pipeline"]
    args = task["args"]

    if args.get("dir", None):
        # os.chdir("/home/njaal")
        # os.chdir(args["dir"])
        cc.log.debug("W2V directory '%s'" % args["dir"])

    if args.get("format", None):
        cmd.extend(["-f", args["format"]])

    if args.get("segments", None):
        cmd.extend(["-i", args["segments"]])

    if args.get("model", None):
        cmd.extend(["-m", args["model"]])
    else:
        if args.get("lang", "no") == "no":
            # cmd.extend(["-m", "NbAiLab/nb-wav2vec2-1b-bokmaal"])
            cmd.extend(["-m", "NbAiLab/wav2vec2--1b-npsc-nst-bokmaal"])
        else:
            cmd.extend(["-m", "facebook/wav2vec2-base-960h"])

    cmd.append(args.get("mode", "transcribe"))

    dst = args.get("dst", os.path.splitext(args["src"])[0] + ".csv")

    cmd.extend([args["src"], dst])
    retval = {"dst": dst}

    # As long as caching doesn't work, check for existance of file
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        cc.log.warning("Cache failed to catch this one")
        return 100, retval

    print("Will run")
    print(" ".join(cmd))

    cc.log.debug(" ".join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    fcntl.fcntl(p.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
    fcntl.fcntl(p.stderr, fcntl.F_SETFL, os.O_NONBLOCK)
    progress = 0
    while not stop_event.isSet():

        if p.poll() is not None:
            # Done
            if p.poll() == 0:
                progress = 100
                retval["result"] = "ok"
                break
            raise Exception("w2vtranscriber failed with exit value %s" % p.poll())

        ready = select.select([p.stdout, p.stderr], [], [], 1.0)[0]
        for fd in ready:

            if fd == p.stdout:
                # Rather do some progress here?
                msg = fd.read().strip()
                if msg:
                    cc.log.debug(msg)
            else:
                msg = fd.read().strip()
                if msg:
                    cc.log.warning(msg)

    if stop_event.isSet():
        try:
            cc.log.info("Terminating transcription")
            p.terminate()
        except Exception:
            pass

    return progress, retval
