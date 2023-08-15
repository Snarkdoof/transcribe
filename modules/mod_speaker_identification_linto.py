import json
import operator
import time
import re
import math
import copy
import os
import pickle
import base64



ccmodule = {
    "description": "Identify speakers based on Linto stuff",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Media source file",
        "vtt": "Subtitle file (created by Whisper for example)",
        "people": "Already known list of people (if available) [people_dir/name or path, ...]",
        "NOPE-people_map": "A list of entries of known speakers, for example introductions in podcasts, tags: start, end, <name>, <avatar>, <filename>",
        "guess_people": "Try to compare identified voices with known people",
        "peopledb": "If you have a database of people (file dir), it will look here for known voices",
        "cutoff": "How close match to regard as a person - default 0.1, higher number = more closely",
        "dst": "Destination subtitle json file",
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
    from diarization.processing.speakerdiarization import SpeakerDiarization
    import torch
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

    def _load_model(self, model_id="nvidia/speakerverification_en_titanet_large"):

        model_id = "titanet_large"
        if self.last_model_id != model_id:
            # Free existing?
            self.last_model_id = model_id
            self.model = speaker_model = nemo_asr.models.EncDecSpeakerLabelModel.from_pretrained(model_id)

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

    def run_diarization(self, filename, num_speakers=None, max_speakers=None):
        diarizationworker = SpeakerDiarization()
        result = diarizationworker.run(filename, number_speaker=num_speakers, max_speaker=max_speakers)
        response = diarizationworker.format_response(result)
        return response

    def _find_segment(self, start, end, segments):
        """
        Find a segment for the given start,end - if no segment overlaps
        start/end, None is returned.
        """
        for segment in segments:
            if segment["seg_begin"] >= start and segment["seg_end"] <= end:
                return segment
        return None

    def load_people(self, wavfile, segments, subs):
        """
        Segments can span many subtitltes, including silence etc. Use long
        subs as timestamps
        """

        # First we make a list of a few long subtitles for each detected person
        speakers = {}
        for sub in subs:
            if sub["end"] - sub["start"] < 5:
                continue

            # Found a pretty long subtitle, who is the speaker?
            segment = self._find_segment(sub["start"], sub["end"], segments)
            if not segment:
                continue  # No well overlapping segment

            # We have a speaker!
            if segments["spk_id"] not in speakers:
                speakers[segments["spk_id"]] = [sub]
            elif len(speakers[segments["spk_id"]]) >= 3:
                continue  # Have enough samples
            else:
                speakers[segments["spk_id"]].append(sub)

        # We now have up to three samples for each speaker, let's load the embeddings
        embeddings = {}
        for speaker in speakers:
            embeddings[speaker] = self.load_embeddings(wavfile, speakers[speaker])
            # [self.get_embedding(wavfile, sub["start"], sub["end"]) for sub in speakers[speaker]]

        return embeddings

    def identify_speakers(people, known_people, cutoff=0.35):
        # Initialize the resulting mapping
        speaker_mapping = {}

        for person, embeddings in people.items():
            # Initialize the highest similarity and most similar known person
            max_similarity = 0
            most_similar_person = None

            for known_person, known_embeddings in known_people.items():
                for embedding in embeddings:
                    for known_embedding in known_embeddings:
                        similarity = self.compare_embeddings(embedding, known_embedding)
                        if similarity > max_similarity:
                            max_similarity = similarity
                            most_similar_person = known_person

            # If the highest similarity is above the cutoff, add a mapping from the person to the known person
            if max_similarity >= cutoff:
                people[person]["name"] = most_similar_person
                people[person]["name_similarity"] = max_similarity
                speaker_mapping[person] = most_similar_person

        return speaker_mapping


    def update_subtitles(subs, speakers, speaker_mapping):
        """
        Update the subtitles based on segments (spk_id) to person.
        If a speaker id is lacking in the mapping, just use the id
        """

        def calculate_overlap(start1, end1, start2, end2):
            """Helper function to calculate the overlap between two time ranges"""
            return max(0, min(end1, end2) - max(start1, start2))

        for sub in subs:
            # Initialize the speaker to None and max overlap to 0
            sub['speaker'] = None
            max_overlap = 0
            for seg in speakers['segments']:
                overlap = calculate_overlap(seg['seg_begin'], seg['seg_end'], sub['start'], sub['end'])
                if overlap > max_overlap:
                    max_overlap = overlap
                    if seg['spk_id'] in speaker_mapping:
                        sub['who'] = speaker_mapping[seg['spk_id']]
                    else:
                        sub['who'] = seg['spk_id']


def process_task(cc, task, stop_event):
    args = task["args"]

    src = args["src"]
    vtt = args.get("vtt", None)
    dst = args["dst"]  # JSON subtitle file
    speakers = dst.replace("_subs.json", "_speakers.json")
    cutoff = args.get("cutoff", 0.10)

    people_dir = args.get("people_dir", None)
    people_src = args.get("people", "")
    guess_people = args.get("guess_people", True)
    castsource = speakers.replace("_speakers.json", "_people.json")

    people_list = args.get("people", [])

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

    cc.status["progress"] = 1


    speakers = vc.run_diarization(src, num_speakers=None, max_speakers=None)
    cc.status["progress"] = 50

    # We first load embeddings for each identified speaker, using timestamps from
    # subtitles to get good samples
    people = vc.load_people(src, speakers["segments"], subs)

    # Load the given people (if any)
    known_people = None
    known_items = {}
    if os.path.exists(people_src) and os.path.getsize(people_src) > 10:
        cc.log.info("Loading candidate people from '%s'" % people_src)
        known_items = vc.load_person_list(people_src, people_dir)

        cc.log.info("Loaded %d candidates" % len(known_items))

        # Find best matches
        cc.status["status"] = "Matching"
        print("Finding best matches based on %d known items" % len(known_items))
        # best_matches = vc.find_best_matches_known_items(known_items, embeddings)
        speaker_mapping = vc.identify_speakers(people, known_items)

    # If we didn't get specific people and we have a database directory, load those
    if people_dir and os.path.isdir(people_dir):
        # Check if we have any people that have not been identified yet
        if len(speaker_mapping) != len(people):
            raise Exception("Missing people but not implemented DB search")

    if len(speaker_mapping) != len(people):
        cc.log.warning("Didn't identify all speakers, only {} of {}"\
                       .format(len(speaker_mapping), len(people)))

    cc.status["progress"] = 95
    cc.status["state"] = "Updating subtitles"
    vc.update_subtitles(subs, speakers, speaker_mapping)

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
    import pickle
    import base64

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
