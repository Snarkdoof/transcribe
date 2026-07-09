# Agent Map - Transcribe Pipeline

## A. System Architecture
This project is a distributed audio/video transcription pipeline built on top of the CryoCore and CryoCloud task frameworks. It uses a workflow-based execution model where jobs are queued and monitored using MySQL/MariaDB database configurations on a central root node. Audio transcription is executed on GPU-enabled worker nodes using Whisper models inside Docker containers, with post-processing tasks like speaker diarization (using MediaPipe and Hugging Face) and subtitle formatting. The root node exposes watch ports via CryoCloud netwatcher and triggers webhooks upon successful pipeline completion.

## B. Core Directory Index
* [modules/](file:///home/njaal/git/transcribe/modules/) - Contains the pipeline step modules (Python scripts starting with `mod_`) executing tasks like Whisper transcription, audio extraction, formatting, and speaker identification.
* [modules/libmediapipe/](file:///home/njaal/git/transcribe/modules/libmediapipe/) - Local helper modules for video and facial feature analysis using MediaPipe (pose estimation, face detection).
* [workernode/](file:///home/njaal/git/transcribe/workernode/) - Contains startup, shutdown, and status monitoring scripts for setting up GPU and CPU processing worker nodes.
* [environments/](file:///home/njaal/git/transcribe/environments/) - Contains Dockerfiles and python requirement files for building Whisper and WhisperX runtime containers.
* [tv2/](file:///home/njaal/git/transcribe/tv2/) - Contains post-processing scripts specifically tailored for TV2 channel output workflows.
* [memorytest/](file:///home/njaal/git/transcribe/memorytest/) - Test scripts and data for measuring memory usage of diarization and transcription workflows.

## C. Key Data/Type Routes
* Pipeline Input Schema -> [nettranscribe.schema](file:///home/njaal/git/transcribe/nettranscribe.schema)
* Default Pipeline Workflow Config -> [nettranscribe.json](file:///home/njaal/git/transcribe/nettranscribe.json)
* Advanced Whisper Workflow Config -> [whisper.json](file:///home/njaal/git/transcribe/whisper.json)
* TV2 Skole Pipeline Workflow Config -> [nettranscribe_tv2skole.json](file:///home/njaal/git/transcribe/nettranscribe_tv2skole.json)

## D. Data Flow / Request Lifecycle
1. **Request Intake:** `netwatcher` (listening on port 9996) receives a webhook or transcription request containing the video/audio URL, validates it against [nettranscribe.schema](file:///home/njaal/git/transcribe/nettranscribe.schema).
2. **Server Check:** `mod_gcloud` checks if processing GPU/CPU instances are active on Google Cloud Platform and boots them if necessary.
3. **Data Preparation:** `mod_prep` / `mod_prep_net` downloads the media content to the shared storage `/data/` and configures target output directories.
4. **Audio Extraction:** `ffmpeg` extracts a 16kHz mono WAV file from the source video/audio.
5. **Speech Detection & Transcription:** `mod_detect_voice` performs voice activity detection, and `mod_whisper` runs speech-to-text models (Whisper) inside a Docker container.
6. **Diarization & Alignment:** `mod_speaker_identification2` identifies speakers and aligns subtitles with timestamps.
7. **Reformatting:** `mod_reformat2` wraps subtitles to correct line lengths and structures the text.
8. **Delivery & Callback:** `mod_publish2` syncs output files to a web server via rsync, and `mod_callback` sends webhook notifications back to the caller with transcription links.
