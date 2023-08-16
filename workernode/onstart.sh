#!/bin/bash

sudo mkfs.ext2 /dev/nvme0n1 
sudo mount /dev/nvme0n1 /scratch
sudo mount /data
mkdir /tmp/cache

sudo chown cryocore /scratch
sudo chown -R cryocore /tmp

rsync -r /data/models /scratch/ --size-only
sudo chown cryocore -R /scratch/

screen -L -Logfile /home/cryocore/stopifidle.term -d -m -S stopifidle /data/stop
ifidle

cd git/cryonite/microservices/transcribe
sudo -u cryocore git pull
echo "Starting nodes"

sudo -u cryocore /home/cryocore/start_workers.sh
echo "Startup OK"
