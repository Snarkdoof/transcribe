#!/bin/bash

if blkid /dev/nvme0n1 | grep ext2; then
  echo "Filesystem already exists, gambling that it's fine"
else
  sudo mkfs.ext2 /dev/nvme0n1 
fi
sudo mount /dev/nvme0n1 /scratch
sudo mount /data
mkdir /tmp/cache

sudo chown cryocore /scratch
sudo chown -R cryocore /tmp

rsync -r /data/models /scratch/ --size-only
sudo chown cryocore -R /scratch/

cd /home/cryocore/git/transcribe
sudo -u cryocore git pull

screen -L -Logfile /home/cryocore/git/transcribe/workernode/stopifidle.term -d -m -S stopifidle /home/cryocore/git/transcribe/workernode/stopifidle

echo "Starting nodes"

sudo -u cryocore /home/cryocore/git/transcribe/workernode/start_workers.sh
echo "Startup OK"
