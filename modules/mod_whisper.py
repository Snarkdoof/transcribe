import subprocess
import fcntl
import os
import select
import copy
import re
import json

try:
    # If we're using the API
    # import whisper_timestamped as whisper
    # import whisper
    CANRUN = True
except:
    print("Can't run whisper in this environment")
    CANRUN = False


ccmodule = {
    "description": "Transcribe a media file",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source file to transcribe",
        "model": "tiny.en, tiny, base.en, base, small.en, small medium.en, medium, large. Default large",
        "task": "transcribe or translate (to english)",
        "lang": "Language, default autodetect",
        "dir": "Directory to place files",
        "reprocess": "Force reprocessing, default False", 
        "initial_promot": "Provide context before the first audio",
        "use_api": "Use Whisper API, don't run the actual process",
        "segments": "If API is used, segments can be sent in and long pauses will be ignored",
        "model_dir": "Default model directory for local models, default /scratch/models/"
    },
    "outputs": {
        "dst": "Output file (VTT)",
        "dst_txt": "Output file (Text)",
        "dst_words": "JSON file with word timestamps (if available)"
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


class Model:
    instance = None
    loaded_model = None

    @staticmethod
    def get(model, device):
        import whisper_timestamped as whisper
        if not Model.instance or Model.loaded_model != model:
            Model.instance = whisper.load_model(model, device=device)
            Model.loaded_model = model
        return Model.instance


def run_whisper(cc, src, dst_dir, model, lang, stop_event, reprocess=False):
    # cmd = ["whisper", "--output_dir", dst_dir, "--model", model, "--word_timestamps", "True"]
    cmd = ["whisper_timestamped", "--output_dir", dst_dir, "--model", model, "--vad", "True", "--accurate"]
    if lang:
        cmd.extend(["--lang", lang])
    cmd.append(src)
    cc.log.info(" ".join(cmd))
    progress = 0
    cc.status["progress"] = 0
    name = os.path.basename(src)
    retval = {
        "dst": os.path.join(dst_dir, name) + ".vtt",
        "dst_txt": os.path.join(dst_dir, name) + ".txt",
        "dst_words": os.path.join(dst_dir, name) + ".words.json"
    }

    if not reprocess and os.path.exists(retval["dst_words"]) and os.path.getsize(retval["dst_words"]) > 0:
        return 100, retval

    cc.log.warning(str(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    fcntl.fcntl(p.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
    fcntl.fcntl(p.stderr, fcntl.F_SETFL, os.O_NONBLOCK)
    while not stop_event.isSet():

        if p.poll() is not None:
            # Done
            if p.poll() == 0:
                progress = 100
                cc.status["progress"] = progress
                return progress, retval
            raise Exception("w2vtranscriber failed with exit value %s" % p.poll())

        ready = select.select([p.stdout, p.stderr], [], [], 1.0)[0]
        for fd in ready:

            if fd == p.stdout:
                progress = 10
                # Rather do some progress here?
                msg = fd.read().strip()
                if msg:
                    cc.log.debug(msg)
            else:
                msg = fd.read().strip()
                if msg:

                    # decode the byte string to a regular string using UTF-8 encoding
                    decoded_str = msg.decode('utf-8')

                    # use a regular expression to find the percentage value
                    match = re.search(r'(\d+)%', decoded_str)

                    # if a match is found, convert it to an integer
                    if match is not None:
                        progress = int(match.group(1))
                        cc.status["progress"] = progress

                    cc.log.warning(msg)

    if stop_event.isSet():
        try:
            cc.log.info("Terminating transcription")
            p.terminate()
            retval["result"] = "terminated"
        except Exception:
            pass
        raise Exception("Terminated")

    raise Exception("Whisper failed")

def load_segment_file(filename, max_break=0.4, min_segment_length=0.6):

    with open(filename, "r") as f:
        if filename.endswith("json"):
            data = json.load(f)
        else:
            # CSV
            data = []
            items = f.readline().strip().split(",")  # the headings
            for line in f.readlines():
                entries = line.strip().split(",")
                item = {items[i]: entries[i] for i in range(len(items))}
                item["start"] = float(item["start"])
                item["end"] = float(item["end"])
                data.append(item)
        
        # We don't want to do all segments, we want to create larger segments
        # where there is an actual break
        segments = []
        for segment in data:
            # We skip very short segments
            if segment["end"] - segment["start"] < min_segment_length:
                continue

            if len(segments) == 0:
                segments.append(segment)
            else:
                if segment["start"] - segments[-1]["end"] < max_break:
                    segments[-1]["end"] = segment["end"]
                else:
                    # New segment
                    segments.append(segment)                

        return segments


def merge(target, item, timeoffset):
    if "text" not in target:
        raise Exception("Internal: Missing 'text' in target '{}'".format(str(target)))
    if "text" not in item:
        raise Exception("Internal: Missing 'text' in item '{}'".format(str(item)))
    target["text"] += item["text"]
    for segment in item["segments"]:
        del segment["tokens"]
        updated_segment = copy.deepcopy(segment)
        for word in updated_segment["words"]:
            word["start"] += timeoffset
            word["end"] += timeoffset

        updated_segment["start"] = updated_segment["words"][0]["start"]
        updated_segment["end"] = updated_segment["words"][-1]["end"]

        target["segments"].append(updated_segment)

def fix_words(res):
    """
    For some reason, the words are expected to be "word" but it's now called "text".
    It's likely some issues with whisper and whisper_timestamped
    """

    for segment in res["segments"]:
        for word in segment["words"]:
            if "text" in word:
                word["word"] = word["text"]

    return res


def process_task(cc, task, stop_event):

    print("MOD_WHISPER", task)

    args = task["args"]

    model = args.get("model", "large-v2")
    model_dir = args.get("model_dir", "/scratch/models/")
    if os.path.exists(os.path.join(model_dir, model)):
        model = os.path.join(model_dir, model)
    elif os.path.exists(os.path.join(model_dir, model + ".bin")):
        model = os.path.join(model_dir, model + ".bin")

    lang = args.get("lang", None)
    if lang == "" or lang == "auto":
        lang = None
    src = args["src"]
    use_api = args.get("use_api", False)
    segment_file = args.get("segments", None)
    dst_dir = args.get("dir", "/tmp")
    patience = args.get("patience", None)
    initial_prompt = args.get("initial_prompt", None)
    reprocess = args.get("reprocess", False)

    base_dst = os.path.splitext(os.path.join(dst_dir, os.path.basename(src)))[0]
    retval = {
        "dst": base_dst + ".vtt",
        "dst_txt": base_dst + ".txt",
        "dst_words": base_dst + "_words.json"
    }

    dst = retval["dst"]
    # As long as caching doesn't work, check for existence of file
    cc.log.info("Whisper destination is '{}".format(dst))
    cc.log.info("Using model '{}'".format(model))

    if not reprocess and os.path.exists(dst) and os.path.getsize(dst) > 0:
        cc.log.warning("Cache failed to catch this one")
        return 100, retval


    # Run from commandline or via API
    if not use_api:
        try:
            return run_whisper(cc, src, dst_dir, model, lang, stop_event, reprocess)
        except:
            # Try once more after a bit - we seem to get an issue once in a while where a 
            # directory exists while being created - possible sync issue?
            import random
            import time
            time.sleep(random.random() * 10)
            return run_whisper(cc, src, dst_dir, model, lang, stop_event, reprocess)

    # We're using the API, that means we run whisper_timestamped for now
    import whisper_timestamped as whisper
    model = Model.get(model, device=args.get("device", "cuda:0"))
    # What happened to "patience?"

    # If we're "streaming", this is likely not too smart, use normal whisper?
    audio = whisper.load_audio(src)

    # Ignore segments fully - DEBUG
    if 0:
        res = whisper.transcribe(model, audio, language=lang,            
                             beam_size=5, best_of=5,
                             temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0))
    else:
        # We should use VAD to ensure that we avoid large pauses - these will
        # confuse timestamps
        segments = [{"start": 0, "end": audio.shape[0]/16000.}]  # Default the whole file
        if segment_file:
            segments = load_segment_file(segment_file)

        res = {"text": "", "segments": []}
        DBG = []

        for segment in segments:
            startsample = segment["start"] * 16000
            endsample = segment["end"] * 16000
            cc.log.info(segment)
            cc.log.info("   {} -> {}".format(startsample, endsample))
            r = whisper.transcribe(model, audio[int(startsample):int(endsample)], language=lang,            
                                 beam_size=5, best_of=5,
                                 temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0))

            DBG.append({"segment": segment, "result": r})
            # Need to re-timestamp everything....
            try:
                merge(res, r, segment["start"])
            except Exception as e:
                cc.log.exception("Processing segment {} -> {}".format(segment["start"], segment["end"]))

        with open("/tmp/dbg_whisper.json", "w") as f:
            json.dump(DBG, f)
    res = fix_words(res)

    # Save it to the destination
    with open(retval["dst_words"], "w") as f:
        json.dump(res, f, indent=" ")

    for s in res["segments"]:
        del s["words"] 

    with open(dst, "w") as f:
       writer = whisper.utils.WriteVTT(dst_dir)
       writer.write_result(res, f)
 
    with open(retval["dst_txt"], "w") as f:
        writer = whisper.utils.WriteTXT(dst_dir)
        writer.write_result(res, f)


    return 100, retval
