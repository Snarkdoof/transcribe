
from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector
import librosa as lb
import torch
import os
import math

# Load test data
data = []
with open("data.csv", "r") as f:
    for line in f.readlines():
        start, stop = line.split(",", 3)[1:3]
        data.append((float(start), float(stop)))
    print("Read %d data points" % len(data))


filename = "audio.wav"

model_id = 'microsoft/wavlm-base-plus-sv'
device = "cuda:0"
feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_id)
model = WavLMForXVector.from_pretrained(model_id).to(device)

size_compared = 0


def compare(idx1, idx2):

    if data[idx1][1] - data[idx1][0] < 0.2:
        return 0
    if data[idx2][1] - data[idx2][0] < 0.2:
        return 0

    return compare_raw(data[idx1][0], data[idx1][1], data[idx2][0], data[idx2][1])


def compare_raw(start1, end1, start2, end2):

    waveform1, rate1 = lb.load(filename, sr=16000,
                               offset=start1,
                               duration=min(10, end1 - start1))
    waveform2, rate2 = lb.load(filename, sr=16000,
                               offset=start2,
                               duration=min(10, end2 - start2))

    audio = [waveform1, waveform2]
    inputs = feature_extractor(audio, padding=True, return_tensors="pt", sampling_rate=16000)
    inputs.to(device)
    embeddings = model(**inputs).embeddings.to(device)
    embeddings = torch.nn.functional.normalize(embeddings, dim=-1).cpu()
    # the resulting embeddings can be used for cosine similarity-based retrieval
    cosine_sim = torch.nn.CosineSimilarity(dim=-1)
    similarity = cosine_sim(embeddings[0], embeddings[1])
    print("%7.2f-%7.2f, %7.2f-%7.2f: %.2f" % (start1, end1, start2, end2, similarity))
    return similarity

# Compare files (this isn't the actual files I compare, but see if we can
# trigger the issue)


# This is OK
if 0:
    for i in range(100):
        compare(0, 81)


# Crashes on 0, 81 every time
if 0:
    for x in range(0, 5):
        for y in range(5, len(data)):
            compare(x, y)


# This still works perfectly...
if 0:
    import random
    for i in range(10000):
        print(i, end=": ")
        x = random.randint(0, len(data) - 1)
        y = random.randint(0, len(data) - 1)
        compare(x, y)


# Do the same ones CC does
if 1:
    with open("/tmp/mod_speaker_identification.csv", "r") as f:
        comparisons = []
        for line in f.readlines():
            start1, end1, start2, end2 = line.split(",")

            compare_raw(float(start1), float(end1), float(start2), float(end2))

