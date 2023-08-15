import os.path


try:
    from transformers import Wav2Vec2Tokenizer, Wav2Vec2ForCTC
    import librosa as lb
    import torch
    CANRUN = True
except Exception:
    CANRUN = False


ccmodule = {
    "description": "Transcribe a WAV file to English",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source file to transcribe",
        "dst": "Destination file",
        "model": "The model to use, default is 'facebook/wav2vec2-base-960h'",
        "dir": "Where to find w2vtranscriber",
        "chunk_size_s": "Chunk size in seconds"
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


class Transcriber:
    instance = None

    @staticmethod
    def get():
        if not Transcriber.instance:
            Transcriber.instance = Transcriber()
        return Transcriber.instance

    def __init__(self):

        self.tokenizer = None
        self.model = None
        self.tokenizerID = ""
        self.modelID = ""

    def get_model(self, modelID):
        if not self.model or modelID != self.modelID:
            self.modelID = modelID
            self.model = Wav2Vec2ForCTC.from_pretrained(modelID)
        return self.model

    def get_tokenizer(self, modelID):
        if not self.tokenizer or modelID != self.tokenizerID:
            self.tokenizerID = modelID
            self.tokenizer = Wav2Vec2Tokenizer.from_pretrained(modelID)
        return self.tokenizer


def process_task(cc, task):
    args = task["args"]

    dst = args.get("dst", os.path.splitext(args["src"])[0] + ".csv")

    args["dst"] = dst

    m = args.get("model", 'facebook/wav2vec2-base-960h')

    transcriber = Transcriber.get()

    model = transcriber.get_model(m)
    tokenizer = transcriber.get_tokenizer(m)

    res = []
    offset = 0
    chunk_size_s = args.get("chunk_size_s", "10")

    while True:

        # Read the sound file
        print("Reading file", offset, chunk_size_s)
        waveform, rate = lb.load(args["src"], sr=16000, offset=offset, duration=chunk_size_s)
        offset += chunk_size_s

        print("Waveform", dir(waveform), rate)

        # Tokenize the waveform
        cc.log.info("Tokenizer running")
        input_values = tokenizer(waveform, return_tensors='pt').input_values

        cc.log.info("Geting logits")
        # Retrieve logits from the model
        logits = model(input_values).logits

        cc.log.info("argmax")
        # Take argmax value and decode into transcription
        predicted_ids = torch.argmax(logits, dim=-1)

        cc.log.info("Batch decode")
        transcription = tokenizer.batch_decode(predicted_ids)
        res.append(transcription)

    with open(args["dst"], "w") as f:
        f.write(transcription)

    return 100, {"result": "ok", "dst": args["dst"]}
