import json
import operator
import time
import re
import math

try:
    from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector
    import librosa as lb
    import torch
    import os
    CANRUN = True
except Exception:
    CANRUN = False

"""
Takes in a set of segments for a wav file, analyses it based on the sentences,
not the timestamps.

If multiple people are detected, the segment will be split to reflect it
"""

ccmodule = {
    "description": "Identify speakers",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source file to detect from (WAVE file)",
        "segments": "segment file - csv or json",
        "dst": "Destination (csv or json) for segments (also a _cast.json file will be created if json). Makes one if blank",
        "threshold": "Threshold for similarity (fraction), default 0.83",
        "max_segments_per_person": "Maximum segments to remember for each person, default 3",
        "max_length": "Max length of audio, default 10s",
        "autosplit": "Automatically split base on punctuation. Default true",
        "skip_start_s": "Skip the first given seconds of the programme (type the intro)"
    },
    "outputs": {
        "cast": "JSON file with cast members (if json output)",
        "dst": "JSON or CSV file with updated segments"
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


class VoiceCompare():
    def __init__(self, log):

        self.model = None
        self.feature_extractor = None
        self.last_model_id = None
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.model_cpu = None
        self._num_cpu_runs = 0
        self.log = log
        self._dbg = open("/tmp/mod_speaker_identification.csv", "w")

    def _load_model(self, model_id='microsoft/wavlm-base-plus-sv'):

        if self.last_model_id != model_id:
            # Free existing?
            self.last_model_id = model_id
            self.feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_id)
            self.model = WavLMForXVector.from_pretrained(model_id).to(self.device)

        if not self.model_cpu:
            if self.device != "cpu":
                self.model_cpu = WavLMForXVector.from_pretrained(model_id)  # , low_cpu_mem_usage=True).to("cpu")
            else:
                self.model_cpu = self.model

    def compare_wav(self, file1, file2, model=None, force_cpu=False, max_length=10.0):
        """
        Compare the two files and see if the speaker is the same
        """

        if not os.path.exists(file1):
            raise Exception("Missing file '%s'" % file1)
        if not os.path.exists(file2):
            raise Exception("Missing file '%s'" % file2)
        waveform1, rate1 = lb.load(file1, sr=16000, duration=max_length)
        waveform2, rate2 = lb.load(file2, sr=16000, duration=max_length)

        return self.compare_raw(waveform1, waveform2, model)

    def compare_raw(self, data1, data2, model=None, cpu_backup=False):

        if model:
            self._load_model(model)
        else:
            self._load_model()
        device = self.device

        print("COMPARE %s vs %s" % (len(data1), len(data2)))

        audio = [data1, data2]
        inputs = self.feature_extractor(audio, padding=True, return_tensors="pt", sampling_rate=16000)
        for i in range(2):
            try:
                inputs.to(device)
                if device == "cpu":
                    embeddings = self.model_cpu(**inputs).embeddings.to(device)
                else:
                    embeddings = self.model(**inputs).embeddings.to(device)
                embeddings = torch.nn.functional.normalize(embeddings, dim=-1).cpu()
                if i > 0:
                    print("*************** IT WORKED ***************")
                    self._num_cpu_runs += 1

                    if self._num_cpu_runs > 100000000:
                        print("Reloading model to avoid memory issues")
                        self.model_cpu = None
                        self._num_cpu_runs = 0
                break
            except Exception as e:
                if cpu_backup and device != "cpu":
                    device = "cpu"
                    print("  -*-*- Retrying on CPU")
                else:
                    # torch.cuda.empty_cache()  # Does NOTHING
                    import traceback
                    traceback.print_exc()
                    raise e

        # the resulting embeddings can be used for cosine similarity-based retrieval
        cosine_sim = torch.nn.CosineSimilarity(dim=-1)
        similarity = cosine_sim(embeddings[0], embeddings[1])
        return similarity

    def compare_wav_offset(self, file, meta1, meta2, model=None,
                           min_length=0.5, max_length=8.0):
        """
        Meta in format {"start": x.x, "end": y.y}
        """

        # If we're too small, don't bother
        if meta1["end"] - meta1["start"] < min_length:
            print(" ------ TOO SHORT (1)", meta1["end"] - meta1["start"])
            return 0

        # This shouldnt happen
        if meta2["end"] - meta2["start"] < min_length:
            print(" ------ TOO SHORT (2)", meta2["end"] - meta2["start"])
            return 0

        # GPU runs out of memory on this one - is it that a large file fesses things up?
        if self._dbg:
            self._dbg.write("%s,%s,%s,%s\n" % (meta1["start"], meta1["end"], meta2["start"], meta2["end"]))
        print("Loading", (meta1["start"], meta1["end"]), (meta2["start"], meta2["end"]))
        waveform1, rate1 = lb.load(file, sr=16000,
                                   offset=meta1["start"],
                                   duration=min(max_length, meta1["end"] - meta1["start"]))
        waveform2, rate2 = lb.load(file, sr=16000,
                                   offset=meta2["start"],
                                   duration=min(max_length, meta2["end"] - meta1["start"]))
        return self.compare_raw(waveform1, waveform2, model)

    @staticmethod
    def save_segment(source, start, end, max_length=10, trim_percent=5):
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

    @staticmethod
    def read_csv(filename):
        entries = []
        with open(filename, "r") as f:
            for line in f.readlines():
                speaker, start, end, duration, fn, text = line.split(",", 5)

                if not start.replace(".", "").isnumeric():
                    continue  # Bad line

                sub = {
                    "start": float(start),
                    "end": float(end),
                    "who": speaker,
                    "file": fn,
                    "text": text
                }
                entries.append(sub)
        return entries

    def split_entry(self, entry, min_length=0):
        """
        Split an entry based on punctuation - assuming linear timing
        """
        subentries = []
        sentences = re.split("(?<=\!)|(?<=\?)|(?<=\.)", entry["text"].replace("\n", " "))
        # sentences = re.split("(?<=\!)|(?<=\?)|(?<=\.)|(qqq+)|(eee+)|(mmm+)", entry["text"].replace("\n", " "))

        time_pr_char = (entry["end"] - entry["start"]) / float(len(entry["text"]))

        start = entry["start"]
        for s in sentences:
            if not s or not s.strip():
                continue

            e = {k: entry[k] for k in entry}
            e["start"] = start
            e["text"] = s
            e["end"] = start + max(min_length, time_pr_char * len(e["text"]))
            start = e["end"]
            if re.sub("qqq", "", e["text"], flags=re.I).strip():
                subentries.append(e)

        return subentries

    def compare(self, wavfile, person, entry, max_length=10):
        min_match = 1
        max_match = 0
        total_score = 0
        for i2, cmeta in enumerate(person["meta"]):
            try:
                similarity = self.compare_wav_offset(wavfile, cmeta,
                                                     entry, min_length=0.6,
                                                     max_length=max_length)
            except Exception:
                # Likely OOM issue - continue for a few more just in case
                self.log.error("!!! OOM? %s, %s-%s" % (wavfile, str(cmeta), str(entry)))
                continue

            print(" --- %s: score %.2f" % (person["name"], similarity), i2)
            min_match = min(min_match, similarity)
            max_match = max(max_match, similarity)
            total_score += similarity
            if max_match > 0.90:  # We're very sure this is corrent, don't check more
                print(" --- feels good")
                return max_match
                # break
            if min_match < 0.50:
                print("  --- not this one")
                return min_match

            # if similarity < threshold:
            #     break
        # candidates.append((c, max_match))
        # score = float(total_score) / (i2 + 1)
        return max_match
        # return score

    def process_json_subs(self, wavfile, segmentfile, threshold,
                          max_files_per_person, stop_event,
                          autosplit=True, skip_start_s=0, max_length=10):
        cast = []
        if segmentfile.endswith(".json"):
            with open(segmentfile, "r") as f:
                    entries = json.load(f)
        else:
            # CSV
            print("Loading CS segment file", segmentfile)
            entries = VoiceCompare.read_csv(segmentfile)

        fixed_entries = []

        for entry in entries:
            if stop_event.isSet():
                raise Exception("Aborted by user")

            if not entry["text"].strip():
                continue

            if skip_start_s and entry["start"] < skip_start_s:
                fixed_entries.append(entry)
                continue

            # If the entry has multiple sentences, we process them all and
            # see if the same person is identified for all
            # TODO: Perhaps join multiple ones here?
            if autosplit:
                subentries = self.split_entry(entry, min_length=0.81)
            else:
                subentries = [entry]

            for subentry in subentries:
                if stop_event.isSet():
                    raise Exception("Aborted by user")

                try:
                    # Sort list by most recently used
                    cast.sort(key=operator.itemgetter("ts"), reverse=True)
                    found = False

                    candidates = []

                    for c in cast:
                        score = self.compare(wavfile, c, subentry, max_length=max_length)
                        print(c["name"], float(score), subentry["text"])
                        candidates.append((c, score))
                        if score > 0.90:  # Go for it
                            break

                    candidates.sort(key=operator.itemgetter(1), reverse=True)
                    for c, similarity in candidates:
                        # print(" * %s: score %.2f" % (c["name"], min_match), i)
                        if similarity >= threshold:
                            subentry["who"] = c["name"]
                            c["ts"] = time.time()

                            if 0:  # Update the samples list with new samples
                                if subentry["end"] - subentry["start"] > 2.0:
                                    if len(c["meta"]) >= max_files_per_person:
                                        c["meta"].pop(0)
                                    c["meta"].append(subentry)

                            else:
                                if len(c["meta"]) < max_files_per_person and \
                                  subentry["end"] - subentry["start"] > 2.0:
                                    c["meta"].append(subentry)
                            found = True
                            break

                    if not found:
                        # New cast memeber
                        print("New cast member", len(cast))
                        cast.append({
                            "name": "person_%d" % len(cast),
                            "meta": [subentry],
                            "ts": time.time()
                        })
                        subentry["who"] = cast[-1]["name"]
                    print(subentry)
                except Exception as e:
                    self.log.exception("Failed entry '%s': %s" % (str(subentry), e))

            # We're done - now check if the sub entries are the same person, if not, split
            last_person = None
            e = []
            for idx in range(0, len(subentries)):
                if not last_person:  # First
                    last_person = subentries[idx]["who"]
                    e.append(subentries[idx])
                    if idx < len(subentries) - 1:  # Not the last one
                        continue

                # Is this the same person?
                elif subentries[idx]["who"] == last_person:  # Still the same
                    e.append(subentries[idx])
                    if idx < len(subentries) - 1:  # Not the last one
                        continue

                # Different person - we complete the current entry and start a new one
                last_person = subentries[idx]["who"]
                # print("MERGING", e)
                new_entry = {}
                for key in e[0]:
                    new_entry[key] = e[0][key]
                new_entry["text"] = " ".join(x["text"] for x in e)
                new_entry["end"] = e[-1]["end"]
                # print(" ==>", new_entry)
                e = [subentries[idx]]
                fixed_entries.append(new_entry)

            # We don't clean up, this is ok
            # if len(e) > 0:
            #     print("E is", e)
            #    raise Exception("INTERNAL")
        return cast, fixed_entries

    def merge_cast(self, wavfile, cast, entries, max_seen=3, threshold=0.8):
        """
        Checks if some cast members are the same and consolidate their entries.
        max_seen allows to not check those with many sightings against each other.
        """

        # Create a useful view into the entries
        view = {}
        for entry in entries:
            if entry["who"] not in view:
                view[entry["who"]] = []
            view[entry["who"]].append(entry)

        # Look for duplicate cast
        print("Look for dupes")
        dupes = []
        for idx, person in enumerate(cast):
            if len(view[person["name"]]) >= max_seen:
                continue  # Well known cast member
            print(person["name"], len(view[person["name"]]))
            for x in view[person["name"]]:
                print(x)
            found = False
            for meta in person["meta"]:
                for member in cast[idx + 1:]:
                    score = self.compare(wavfile, member, meta)
                    if score > threshold:
                        print("Person", person["name"], "is likely", member["name"])
                        dupes.append((person, member))
                        found = True
                        break
                if found:
                    break

        # MERGE
        print("Should merge")
        for dupe in dupes:
            print(dupe)

        for p1, p2 in dupes:
            # Merge p1 into p2
            for entry in view[p1["name"]]:
                entry["who"] = p2["name"]

            cast.remove(p1)

        return cast, entries


def process_task(cc, task, stop_event):
    args = task["args"]

    src = args["src"]
    segments = args["segments"]
    dst = args.get("dst", None)
    max_length = args.get("max_length", 10)
    if not dst:
        # Create one - we use the same format as input
        n, e = os.path.splitext(segments)
        dst = n + "_ident" + e

    if src.endswith(".json"):
        castfile = dst.replace(".json", "_cast.json")
    else:
        castfile = None

    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        cc.log.warning("Cache didn't catch this one either")
        return 100, {"dst": dst, "cast": castfile}

    autosplit = args.get("autosplit", True)

    threshold = args.get("threshold", 0.83)
    max_segments_per_person = args.get("max_segments_per_person", 3)
    skip_start_s = float(args.get("skip_start_s", 0))

    vc = VoiceCompare(cc.log)

    if 0 and os.path.exists("/tmp/tmp.json"):
        with open("/tmp/tmp.json", "r") as f:
            d = json.load(f)
            cast = d["cast"]
            entries = d["entries"]
    else:
        cast, entries = vc.process_json_subs(src, segments, threshold,
                                             max_segments_per_person, stop_event,
                                             autosplit, skip_start_s)

    with open("/tmp/tmp.json", "w") as f:
        f.write(json.dumps({"cast": cast, "entries": entries}, indent=" "))

    cast, entries = vc.merge_cast(src, cast, entries, threshold=threshold)

    if dst.endswith(".json"):
        with open(dst, "w") as f:
            f.write(json.dumps(entries, indent=" "))

        with open(castfile, "w") as f:
            f.write(json.dumps(cast, indent=" "))
    else:
        # Dump CSV
        with open(dst, "w") as f:
            f.write("speaker,start,end,duration,audio_path,text\n")
            for item in entries:
                if "who" not in item:
                    item["who"] = "unknown"
                f.write("%s,%f,%f,%f,%s, %s\n" % (item["who"],
                                                  item["start"],
                                                  item["end"],
                                                  item["end"] - item["start"],
                                                  src,
                                                  item["text"]))

    return 100, {"dst": dst, "cast": castfile}
