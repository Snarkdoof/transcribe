#!/bin/bash
source .secret

#ccnode --cpus 0 --gpu 0 &

ccworkflow nettranscribe.json  --dir /home/njal_borch/git/transcribe/ --tmpdir /home/cache/transcribe --archivedir /data/outbox/transcribe/  --loglevel DEBUG  --aws_access_key_id $AWS_ACCESS_KEY_ID --aws_secret_access_key $AWS_SECRET_ACCESS_KEY  $@

#ccworkflow nettranscribe.json  --dir /home/njal_borch/git/transcribe/ --tmpdir /home/cache/transcribe --archivedir /data/outbox/transcribe/  --loglevel DEBUG --hf_token $HF_TOKEN $@

