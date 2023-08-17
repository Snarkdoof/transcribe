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

CODE_DIR=/home/cryocore/git/transcribe
cd $CODE_DIR

echo "Updating code base"
sudo -u cryocore git pull

screen -L -Logfile $CODE_DIR/workernode/stopifidle.term -d -m -S stopifidle $CODE_DIR/workernode/stopifidle

echo "Starting nodes"

sudo -u cryocore $CODE_DIR/workernode/start_workers.sh
echo "Startup OK"
