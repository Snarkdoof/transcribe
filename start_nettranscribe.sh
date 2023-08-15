#!/bin/bash

ccnode --cpus 0 --gpu 0 &

ccworkflow nettranscribe.json  --dir /home/cryocore/git/transcribe/ --tmpdir /scratch/transcribe --archivedir /data/transcribe/  --loglevel DEBUG
