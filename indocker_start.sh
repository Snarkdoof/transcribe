#!/bin/bash

# GET THESE FROM SOMEWHERE ELSE, LIKE git secrets OR vault

AWS_ACCESS_KEY_ID=somekey
AWS_SECRET_ACCESS_KEY=anotherkey

cd /jojo/cryocore

service mysql start

mysql < CryoCore/Install/create_db.sql

./bin/ccconfig import CryoCore/Install/defaultConfiguration.xml


cd /jojo
ccnode --num-workers=4 --gpu 2 &

ccworkflow nettranscribe-docker.json --dir /jojo --tempdir /tmp/transcribe --archivedir /data/outbox/transcribe/  --loglevel DEBUG  --aws_access_key_id $AWS_ACCESS_KEY_ID --aws_secret_access_key $AWS_SECRET_ACCESS_KEY $@



