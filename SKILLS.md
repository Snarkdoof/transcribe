# Skills - Transcribe Pipeline API & Workflow Reference

This library provides a distributed media transcription pipeline built on top of CryoCore and CryoCloud.

## 1. API Documentation

### Watcher Endpoint
The pipeline launches an HTTP server (`netwatcher` module) to receive transcription requests.
* **Default Port:** `9996` (configurable via `port` option in [nettranscribe.json](file:///home/njaal/git/transcribe/nettranscribe.json))
* **Request Schema:** [nettranscribe.schema](file:///home/njaal/git/transcribe/nettranscribe.schema)

#### POST Request Payload
```json
{
  "url": "https://example.com/media/audio.mp3",
  "callbackurl": "https://example.com/api/transcribe-callback",
  "contentid": "unique-media-id-123",
  "lang": "no",
  "model": "large-v2",
  "reprocess": false
}
```

* **url** *(string, required)*: The URL of the source media file (video or audio) to transcribe.
* **callbackurl** *(string, required)*: Callback URL triggered when the transcription is complete.
* **contentid** *(string, required)*: Unique identifier of the transcription task.
* **lang** *(string, required)*: Language identifier (e.g., `no`, `en`).
* **model** *(string, optional)*: Whisper model configuration (e.g., `large-v2`).
* **reprocess** *(boolean, optional)*: If `true`, forces reprocessing even if a cached transcript exists.

#### Callback Webhook Payload
Upon completion, the pipeline calls the `callbackurl` with the following parameters:
* **contentid**: The unique identifier passed in the request.
* **weburl**: Root URL where generated resources are hosted.
* **vtt**: Path to the generated WebVTT subtitle file.
* **text**: Path to the raw transcript text file.
* **json**: Path to the JSON word-level timestamps file.
* **model**: The Whisper model used.

---

## 2. Command Line Operations

### Starting the Pipeline Node & Workflow
To start the CryoCloud processing node and load the default nettranscribe workflow:
```bash
# Run from the project root
./start_nettranscribe.sh
```
Internally, this script runs:
```bash
# Spin up CryoCloud node (disabling CPU/GPU processing on root node to act as orchestrator)
ccnode --cpus 0 --gpu 0 &

# Start the workflow using the configuration file
ccworkflow nettranscribe.json \
  --dir /home/cryocore/git/transcribe/ \
  --tmpdir /scratch/transcribe \
  --archivedir /data/transcribe/ \
  --loglevel DEBUG
```

---

## 3. Configuration & Environment Settings

### CryoCore Config Keys
Set parameters in the CryoCore global database configuration:
```bash
# Set default Whisper model
ccconfig add Cryonite.NetTranscriber.model large-v2

# Set local web directory path to save transcription outputs on the web server
ccconfig add Cryonite.NetTranscriber.webroot /var/www/html/transcribe

# Set public web root URL corresponding to the webroot directory
ccconfig add Cryonite.NetTranscriber.weburl https://<yourdomain>/transcribe/
```

### Database Settings (`~/.cryoconfig`)
Each node must point to the MySQL database hosted on the central root node. Set this in the JSON configuration file:
```json
{
  "db_host": "10.128.2.12"
}
```

---

## 4. Workflows

### Default Workflow ([nettranscribe.json](file:///home/njaal/git/transcribe/nettranscribe.json))
A streamlined pipeline suited for typical transcription requests:
1. `netwatcher` receives the request.
2. `mod_gcloud` wakes up GPU workers if needed.
3. `mod_prep_net` downloads the source media to shared storage.
4. `ffmpeg` extracts the audio at 16000Hz mono.
5. `mod_whisper` transcribes audio inside Docker.
6. `mod_reformat2` wraps subtitles to 45 chars max.
7. `mod_callback` sends files and notifies callback URL.

### Advanced Workflow ([whisper.json](file:///home/njaal/git/transcribe/whisper.json))
For advanced transcript formatting and production-quality output:
* **Dynamic Aspect Ratio (DAR):** Uses MediaPipe pose/face detection to adjust scaling.
* **Diarization & Alignment:** Uses Hugging Face & speaker identification (`mod_speaker_identification2`) to map speaker names.
* **Chapters & Summarization:** Uses OpenAI's API to divide the transcript into chapters and generate summaries.
