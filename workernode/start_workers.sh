#!/bin/bash

export PYTHONPATH=/home/cryocore/git/cryocore
export CC_DIR=/home/cryocore/git/cryocloud

echo "Starting CPU node"
screen -d -m -S cpunode -L -Logfile /tmp/cpunode.log /data/cpunode
sleep 1s
echo "Starting GPU nodes"
screen -d -m -S gpunode1 -L -Logfile /tmp/gpunode0.log /data/gpunode0

