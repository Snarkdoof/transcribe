import re
import os
import contextlib
import wave
import json

try:
    import ftfy
    import numpy as np
    CANRUN = True
except Exception:
    CANRUN = False
    print("Missing ftfy")


ccmodule = {
    "description": "Run Whisper from Huggingface using Transformers",
    "depends": [],
    "provides": [],
    "inputs": {
        "model": "Model, default openai/whisper-lagrge-v2",
        "src": "Input file",
        "lang": "Language, default 'en'",
        "task": "transcribe or translate, default transcribe",
        "device": "Force device, otherwise auto-detect",
        "reprocess": "Force reprocessing, default False"
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

class HfWhisper:
    instance = None

    @staticmethod
    def get():
        if not HfWhisper.instance:
            HfWhisper.instance = HfWhisper()
        return HfWhisper.instance

    def __init__(self):

        self.processor = None
        self.model = None
        self.pipeline = None  # Can be a model/processor OR < pipeline
        self.modelID = ""
        self.log = None
        self.pcm_data = b""

    def process_task(self, cc, task):

        self.log = cc.log

        args = task["args"]
        __model_id = args.get("model", "openai/whisper-large-v2")
        max_len = args.get("max_length", 512)
        self.device = args.get("device", None)
        if not self.device:
            import torch
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"

        if "dst" not in args:
            d, f = os.path.split(args["src"])
            args["dst"] = os.path.join(d, "transformed-%s" % f)

        if not args.get("reprocess", False):
            if os.path.exists(args["dst"]) and os.path.getsize(args["dst"]) > 0:
                cc.log.warning("Cache failed to catch this one")
                return 100, {"result": "ok", "dst": args["dst"]}


        if not self.processor or self.modelID != __model_id:
            self.modelID = __model_id
            lang = args.get("lang", "en")
            if self.modelID.startswith("openai"):
                from transformers import WhisperProcessor, WhisperForConditionalGeneration
                self.processor = WhisperProcessor.from_pretrained(self.modelID)
                self.model = WhisperForConditionalGeneration.from_pretrained(self.modelID).to(self.device)
                self._forced_decoder_ids = self.processor.get_decoder_prompt_ids(language=lang, task="transcribe", no_timestamps=False)
                self.model.forced_decoder_ids = self._forced_decoder_ids
            else:
                from transformers import pipeline
                self.pipeline = pipeline(
                    task="automatic-speech-recognition",
                    model=self.modelID,
                    chunk_length_s=29,
                    device=self.device
                )
                from transformers import WhisperProcessor
                self.processor = WhisperProcessor.from_pretrained("NbAiLab/whisper-norwegian-small-test")
                # processor = WhisperProcessor.from_pretrained("openai/whisper-large-v2")
                self.pipeline.model.config.forced_decoder_ids = \
                   self.processor.get_decoder_prompt_ids(language=lang,
                                                         task="transcribe",
                                                         no_timestamps=False)
                self.model = self.pipeline.model
                # self.pipeline.model.config.forced_decoder_ids = pipe.processor.get_decoder_prompt_ids(language=lang, task="transcribe")

        # text = self._whisper(args["src"])

        # Test given times
        audio, sample_rate = self.read_wave(args["src"])
        subs = []
        if args["segments"].endswith("csv"):
            with open(args["segments"], "r") as f:
                for line in f.readlines():
                    _,start,end, _, _ = line.split(",")
                    if start == "start":
                        continue
                    start = float(start)
                    end = float(end)
                    text = self._whisper(self.get_audio_for_time(start, end))
                    print("%.2f-%.2f: %s" % (start, end, text))
                    items = self._split_text(text[0], start, end)
                    subs.extend(items)
        else:
            MAX_CHARS_PR_SEC = 99
            with open(args["segments"], "r") as f:
                segments = json.load(f)
                for idx, segment in enumerate(segments):
                    if segment["end"] - segment["start"] <= 1:
                        continue
                    start = segment["start"]
                    text = self._whisper(self.get_audio_for_time(start, segment["end"]))
                    print("%.2f-%.2f: %s" % (start, segment["end"], text))
                    l = len(text[0])
                    if l / (segment["end"] - start) > MAX_CHARS_PR_SEC:
                        print("  *** Likely bad", l / (segment["end"] - start))
                        continue
                    items = self._split_text(text[0], segment["start"], segment["end"], segment["who"])
                    subs.extend(items)

        with open("/tmp/peretest.json", "w") as f:
            json.dump(subs, f, indent=" ")
        print("Written to /tmp/peretest.json")

        # We're ready to lock and load!
        output = self.process_audio(args["src"], args["dst"],
                                    args.get("lang", "en"),
                                    args.get("task", "transcribe"))

        with open(args["dst"], "w") as f:
            json.dump(output, f, indent=" ")


        return 100, {"result": "ok", "dst": args["dst"]}

    def _split_text(self, text, start, end, who=None):
        """
        If there are full stops (not too close to the start), we split and
        adjust timestamps based on linear speed.
        Always returns a list of {"start": x, "end": y, "text": text}
        """
        import re
        ret = []
        shortest_sentence = 10
        m = re.split(r'(\.|!|\?)', text)
        if not m:
            ret.append({"start": start, "end": end, "text": text})
        else:
            s_pr_char = (end - start) / float(len(text))
            s = start
            t = ""
            for bit in m:
                t += bit
                if bit == ".":
                    if len(t) > shortest_sentence:
                        e = s + s_pr_char * len(t)
                        ret.append({
                            "start": s,
                            "end": e,
                            "text": t
                            })
                        t = ""
                        s = e
            if t:
                ret.append({
                    "start": s,
                    "end": end,
                    "text": t
                    })

        if who:
            for r in ret:
                r["who"] = who
        return ret

    def read_wave(self, path):
        """Reads a .wav file.

        Takes the path, and returns (PCM audio data, sample rate).
        """
        with contextlib.closing(wave.open(path, 'rb')) as wf:
            num_channels = wf.getnchannels()
            assert num_channels == 1
            sample_width = wf.getsampwidth()
            assert sample_width == 2
            sample_rate = wf.getframerate()
            assert sample_rate in [16000]
            pcm_data = wf.readframes(wf.getnframes())
            self.pcm_data = pcm_data
            return pcm_data, sample_rate

    def frame_generator(self, audio, frame_duration_ms=30000, sample_rate=16000):
        """Generates audio frames from PCM audio data.

        Takes the desired frame duration in milliseconds, the PCM data, and
        the sample rate.

        Yields Frames of the requested duration.
        """
        n = int(sample_rate * (frame_duration_ms / 1000.0) * 2)
        offset = 0
        timestamp = 0.0
        duration = (float(n) / sample_rate) / 2.0
        while offset + n < len(audio):
            yield {"audio": audio[offset:offset + n], "ts": timestamp, "duration": duration}
            timestamp += duration
            offset += n


    def get_timestamp(self, bytenr, sample_rate = 16000):
        return (float(bytenr) / sample_rate) / 2.0

    def get_audio_for_time(self, start, end, sample_rate=16000):
        """
        Return the audio bytes for the given time span
        """

        start_byte = int(sample_rate * 2* start)
        end_byte = int(sample_rate * 2 * end)

        if (end_byte - start_byte) % 4 != 0:
            end_byte -= (end_byte - start_byte) % 4

        if end_byte > len(self.pcm_data):
            raise Exception("NO DATA FOR GIVEN TIME")

        return self.pcm_data[start_byte:end_byte]

    def _whisper(self, audio):
        if self.pipeline and isinstance(audio, str):
            print("Using pipeline")
            res = self.pipeline(audio)
            print("RESULT", res)
            return res["text"]

        audio = np.frombuffer(audio, np.int16).flatten().astype(np.float32) / 32768.0
        input_features = self.processor(audio, return_tensors="pt", sampling_rate=16000).input_features.to(self.device)
        predicted_ids = self.model.generate(input_features)  # , forced_decoder_ids=self._forced_decoder_ids).to(self.device)
        transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)


        m = re.match(".*\|\>([^\<]*)\<\|", transcription[0])
        if m:
            if m.groups()[0].strip().startswith("Undertekster av ") or \
                m.groups()[0].strip().startswith("Teksting av ") or \
                m.groups()[0].strip().startswith("Subtitles by "):
                # Phantom stuff
                return ""
        return transcription

    def process_audio(self, source, destination, lang, task="transcribe"):

        if self.pipeline:
            res = self.pipeline(source)
            print("RESULT", res)
            # TODO STORE IT
            with open("/tmp/" + os.path.basename(source) + ".TXT", "w") as f:
                f.write(res["text"])
            print("Saved to", "/tmp/" + os.path.basename(source) + ".TXT")

        # Load the file 
        audio, sample_rate = self.read_wave(source)
        frames = list(self.frame_generator(audio))

        text = self._whisper(source)
        with open("/tmp/whisperhf.txt", "w") as f:
            f.write(text)

        raise SystemExit()
        # Now we need to pass the audio blocks through the model
        output = []
        for frame in frames:
            print("Processing frame", frame["ts"], len(frame["audio"]), frame["audio"].__class__)
            # audio = np.frombuffer(frame["audio"], dtype=np.float32)
            transcription = self._whisper(frame["audio"])
            output.append({
                "ts": frame["ts"],
                "duration": frame["duration"],
                "text": transcription
            })
            print(transcription)
        return output


def process_task(cc, task):

    transformer = HfWhisper.get()
    return transformer.process_task(cc, task)
