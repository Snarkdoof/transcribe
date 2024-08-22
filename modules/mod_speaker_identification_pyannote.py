import json
import operator
import math
import os
import pickle
import base64


ccmodule = {
    "description": "Identify speakers, requires 16khz audio",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Media source file",
        "vtt": "Subtitle file (created by Whisper for example)",
        "segments": "Detected audio segments",
        "people": "Already known list of people (if available) [people_dir/name or path, ...]",
        "people_dir": "Directory of people (if not absolute paths in people file)",
        "guess_people": "If people are given, still guess for others? Default True",
        "dst": "Destination subtitle json file",
        "cutoff": "How close match to regard as a person - default 0.1, higher number = closer",
        "realign": "Try to realign (resync) subtitles with the sound"
    },
    "outputs": {
        "cast": "JSON file with cast members",
        "dst": "JSON file with updated segments"
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

try:
    import torch
    from pyannote.audio import Pipeline
    import nemo.collections.asr as nemo_asr
    CANRUN = True
except Exception:
    CANRUN = False


class VoiceCompare():
    def __init__(self, log):

        self.model = None
        self.last_model_id = None
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.log = log
        self.cast = []  # We group "seconds" for each speaker
        self.detected_people = {}
        self._cast = {}

    def _load_model(self,
                    model_id="nvidia/speakerverification_en_titanet_large"):

        model_id = "titanet_large"
        if self.last_model_id != model_id:
            # Free existing?
            self.last_model_id = model_id
            self.model = nemo_asr.models.EncDecSpeakerLabelModel.from_pretrained(model_id)

    def compare_embeddings(self, embeddings0, embeddings1):
        # the resulting embeddings can be used for cosine similarity-based retrieval
        cosine_sim = torch.nn.CosineSimilarity(dim=-1)
        similarity = cosine_sim(embeddings0, embeddings1)
        return similarity

    def get_embedding(self, wavfile, start=None, end=None):
        """
        If start and end are given, a temporary file is created and embeddings returned
        """
        self._load_model()

        if start is not None and end is not None:
            try:
                f = self.save_segment(wavfile, start, end, max_length=10000)
                return self.model.get_embedding(f).to(self.device)
            finally:
                try:
                    os.remove(f)
                except Exception:
                    pass
        return self.model.get_embedding(wavfile).to(self.device)

    @staticmethod
    def save_segment(source, start, end, max_length=1, trim_percent=0):
        """
        Create a temporary file  with the given segment
        max_len will limit the max size

        trim_percent will take off the percent (in total) divided by half at
        the beginning and half at the end.
        """
        end = start + min(max_length, end - start)
        length = end - start

        if trim_percent and length > 1.0:  # We only trim if over a second
            start += length * ((trim_percent / 2) / 100.)
            end -= length * ((trim_percent / 2) / 100.)

        import wave
        import tempfile
        dst_file = tempfile.mktemp(suffix=".wav")
        dst = wave.open(dst_file, "w")
        src = wave.open(source, "r")

        # Skip to position
        rate = src.getframerate()
        # Sanity
        if start > src.getnframes() / rate:
            raise Exception("Segment starts after file end, %s, %s" % (start, source))

        src.setpos(math.floor(rate * start))
        data = src.readframes(math.ceil(rate * (end - start)))
        dst.setsampwidth(src.getsampwidth())
        dst.setnchannels(src.getnchannels())
        dst.setframerate(rate)
        dst.writeframes(data)
        return dst_file

    def load_embeddings(self, wavfile, segments, min_time=None, max_time=None):

        embeddings = []
        for segment in segments:
            if min_time and segment["start"] < min_time:
                continue
            if max_time and segment["end"] > max_time:
                break

            SEG_LENGTH = 0.50
            prsec = int(1 / SEG_LENGTH)
            for i in range(0, prsec * math.ceil(segment["end"] - segment["start"])):
                e = min(segment["start"] + SEG_LENGTH + (SEG_LENGTH * i), segment["end"])
                if e - (segment["start"] + (SEG_LENGTH * i)) < SEG_LENGTH:
                    continue  # Too short
                try:
                    embedding = self.get_embedding(wavfile, segment["start"] + (i * SEG_LENGTH), e)
                    embeddings.append(((segment["start"] + (SEG_LENGTH * i), e), embedding))
                except Exception:
                    if self.log:
                        self.log.exception("Failed to get embeddings for %s [%s - %s]" %
                                           (wavfile, segment["start"] + (SEG_LENGTH * i), e))
                    else:  # Only while debugging
                        print("Failed to get embeddings for %s [%s - %s]" %
                              (wavfile, segment["start"] + (SEG_LENGTH * i), e))
                        import traceback
                        traceback.print_exc()
        return embeddings

    def find_best_matches(self, embeddings, safe_hit=0.35):
        best_matches = []
        for x, e0 in enumerate(embeddings):

            # If it's a good match with the previous one, go for that
            if 0 and x > 0:
                s = vc.compare_embeddings(e0[1], embeddings[x - 1][1])
                if s >= safe_hit:
                    print("Quick-hit", x, s)
                    best_matches.append([x, x - 1, s])
                    continue

            max_sim = [None, 0]
            for y, e1 in enumerate(embeddings):
                if y < x + 1:
                    continue
                sim = vc.compare_embeddings(e0[1], e1[1])
                if sim > max_sim[1]:
                    max_sim = [y, sim]
                if sim >= safe_hit:
                    break

            best_matches.append((x, max_sim[0], max_sim[1]))
        return best_matches

    def get_embeddings_by_time(self, embeddings, starttime, endtime):
        """
        Return a loaded embedding for the given time
        """

        ret = []
        for ts, embedding in embeddings:
            if ts[0] >= starttime and ts[1] <= endtime:
                ret.append((ts, embedding))
        return ret


class Diarizer():
    def __init__(self, HF_ACCESS_TOKEN,
                 model="pyannote/speaker-diarization-3.0"):
        self.pipeline = None
        self.model = model
        self.token = HF_ACCESS_TOKEN

    def get_pipeline(self):
        if not self.pipeline:
            self.pipeline = Pipeline.from_pretrained(self.model, 
                                                     self.token)
        return self.pipeline()

    def free_pipeline(self):
        if self.pipeline:
            # Free it
            self.pipeline = None

    def diarize(self, audio_file, gpu=None,
                min_speakers=None, max_speakers=None):

        pipeline = self.get_pipeline()

        if gpu:
            pipeline.to(torch.device(gpu))

        from pyannote.audio.pipelines.utils.hook import ProgressHook
        with ProgressHook() as hook:
            diarization = pipeline(audio_file, hook=hook,
                                   min_speakers=min_speakers,
                                   max_speakers=max_speakers)
        return diarization


def process_task(cc, task, stop_event):
    args = task["args"]

    src = args["src"]
    dst = args["dst"]
    hf_access_token = args["hf_access_token"]
    min_speakers = args.get("min_speakers", None)
    max_speakers = args.get("max_speakers", None)
    gpu = args.get("gpu", None)

    diarizer = Diarizer(hf_access_token)
    res = diarizer.diarize(src, gpu=gpu, max_speakers=max_speakers, min_speakers=min_speakers)

    with open("dst", "w") as f:
        json.dump(res, f, indent=" ")
    return 100, {"dst": dst}

    segment_file = args["segments"]
    vtt = args.get("vtt", None)
    dst = args["dst"]  # JSON subtitle file
    speakers = dst.replace("_subs.json", "_speakers.json")
    cutoff = args.get("cutoff", 0.10)

    people_dir = args.get("people_dir", None)
    people_src = args.get("people", "")
    guess_people = args.get("guess_people", True)
    castsource = speakers.replace("_speakers.json", "_people.json")

    subs = []
    if vtt:
        if not vtt.endswith("json"):
            import mod_reformat
            parser = mod_reformat.SubParser()
            print("Loading subtitles from '%s'" % vtt)
            subs = parser.load_srt(vtt)
        else:
            with open(vtt, "r") as f:
                subs = json.load(f)
        if len(subs) == 0:
            raise Exception("No subtitles in file '%s'" % vtt)
        cc.log.debug("Loaded %d subtitles" % len(subs))

    cc.status["progress"] = 0
    vc = VoiceCompare(cc.log)
    vc._load_model()

    if 0 and os.path.exists(dst) and os.path.getsize(dst) > 10:
        cc.log.warning("Cache didn't catch this one either")
        return 100, {"dst": dst, "cast": castsource}

    if segment_file.endswith(".csv"):
        segments = vc.read_csv(segment_file)
    else:
        raise Exception("Bad file format for segments: '%s'" % segment_file)

    cc.log.debug("Loaded %d segments" % len(segments))

    cc.status["progress"] = 1
    cc.status["state"] = "Loading embeddings"
    embeddings = vc.load_embeddings(src, segments)
    cc.status["progress"] = 5
    cc.log.debug("Loaded %d embeddings" % len(embeddings))
    # TRY THIS:
    # Input a list of people, with start-end for their voices
    # GO through the file and find best match
    known_people = None
    known_items = {}
    if os.path.exists(people_src) and os.path.getsize(people_src) > 10:
        cc.log.info("Loading candidate people from '%s'" % people_src)
        known_items = vc.load_person_list(people_src, people_dir)

        cc.log.info("Loaded %d candidates" % len(known_items))

    if len(known_items) == 0 or guess_people:  # not known_people:
        # Need to guess
        cc.status["state"] = "Auto-detecting people"
        # We could re-use the embeddings here and save us a LOT of time
        known_people = vc.guess_known_items(src, segments, embeddings)
        if len(known_people) == 0:
            raise Exception("Failed to detect any people")

        cc.log.debug("Got %d known items" % len(known_people))
        # DEBUGGING
        c = vc.people_to_cast(src, known_people)
        with open(castsource, "w") as f:
            json.dump(c, f, indent=" ")

        # TODO: Just strip off the timestamps from known_people
        known_items.update(vc.build_known_items(c))
    else:
        # Save cast
        with open(castsource, "w") as f:
            json.dump(vc._cast, f, indent=" ")

    cc.status["progress"] = 15
    cc.status["status"] = "Matching"
    print("Finding best matches based on %d known items" % len(known_items))
    best_matches = vc.find_best_matches_known_items(known_items, embeddings)
    cc.status["progress"] = 55
    cc.status["state"] = "Building cast"
    cast = vc.build_cast_known_items(embeddings, known_items, best_matches, cutoff)
    cc.log.debug("%d cast members" % len(cast))
    # best_matches = vc.find_best_matches(embeddings)
    # cast = vc.build_cast(best_matches, cutoff)
    with open("/tmp/cast.json", "w") as f:
        json.dump(cast, f, indent=" ")
    # RESYNC
    # subs = vc.realign_subs(subs, segments, cast)

    # Go through the segments, find who is the most likely speaker, then update the thing
    cc.status["state"] = "Identify speakers"
    cc.status["progress"] = 75
    for s in subs:
        s["who"] = vc.find_most_likely_speaker(cast, s["start"], s["end"])
        if s["who"] is None:
            print(" ----- FAILED to identify speaker", s)

    # Also dump speakers for visual debugging
    dataset = []
    for person in cast:
        for t in cast[person]:
            t["who"] = person
            dataset.append(t)
    new_speak = []
    dataset.sort(key=operator.itemgetter("start"))
    for speaker in dataset:
        if len(new_speak) == 0:
            new_speak.append(speaker)
            continue

        if speaker["start"] == new_speak[-1]["end"] and speaker["who"] == new_speak[-1]["who"]:
            new_speak[-1]["end"] = speaker["end"]
        else:
            new_speak.append(speaker)
    
    with open(speakers, "w") as f:
        json.dump(new_speak, f, indent=" ")

    cc.status["progress"] = 80

    if args.get("realign", False):
        if not subs:
            raise Exception("Can't realign without subs")
        cc.status["state"] = "Realign subs"
        subs = vc.realign_subs_whisper(src, subs, new_speak, cast)

    # Write the CSV back
    # vc.write_csv(segments, dst)
    if subs:
        with open(dst, "w") as f:
            json.dump(subs, f, indent=" ")

    return 100, {"dst": dst, "cast": castsource}


if __name__ == "__main__":
    # Small tool to create embeddings for people based on a peoples file

    import sys
    with open(sys.argv[1], "r") as f:
        people = json.load(f)

    DBDIR="/home/njaal-local/peopleDB/"

    vc = VoiceCompare(None)
    known_items = vc.build_known_items(people)

    for pid in people:
        person = people[pid]

        if "name" not in person:
            # likely extra colors only, don't worry
            continue

        print("PERSON", person)
        if not isinstance(person["name"], str):
            print("BAD PERSON", person["name"])
            continue

        name = str(person["name"]).replace(" ", "_")
        if "segments" in person:
            del person["segments"]

        person["voice"] = base64.b64encode(pickle.dumps(known_items[pid])).decode("ascii")

        with open(os.path.join(DBDIR, name) + ".json", "w") as f:
            json.dump(person, f)

        # with open(os.path.join(DBDIR, name) + ".embeddings", "wb") as f:
        #    pickle.dump(known_items[pid], f)
