#!/bin/bash

ccworkflow transcribe2.json --dir /home/njaal/git/cryonite/microservices/transcribe/ --src $1 --dst /data/cache/$2 ${@:3}
