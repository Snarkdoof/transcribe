#!/bin/bash

pwd=`pwd`
# Check if the target argument is provided
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <target_directory>"
    exit 1
fi

target="$1"

# Check if the target directory exists
if [ ! -d "$target" ]; then
    echo "Error: Directory $target does not exist."
    exit 1
fi

# Enter the directory
cd "$target" || exit

# Check if "prepare.sh" exists in the directory and run it
if [ -f "prepare.sh" ]; then
    ./prepare.sh
fi

# Run docker build
docker build --build-arg username=$USER --build-arg uid=$UID -t $target .

cd $pwd

echo "OK"