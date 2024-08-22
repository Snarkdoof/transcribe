#!/bin/bash
source .secret

#ccnode --cpus 0 --gpu 0 &

ccworkflow nettranscribe.json  --dir /home/njal_borch/git/transcribe/ --tmpdir /home/cache/transcribe --archivedir /data/outbox/transcribe/  --loglevel DEBUG  $@

#ccworkflow nettranscribe.json  --dir /home/njal_borch/git/transcribe/ --tmpdir /home/cache/transcribe --archivedir /data/outbox/transcribe/  --loglevel DEBUG --hf_token $HF_TOKEN $@

