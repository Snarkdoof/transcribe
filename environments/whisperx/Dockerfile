
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

# FROM nvcr.io/nvidia/pytorch:24.01-py3

# RUN apt update && echo "8\n30\n8\n" | DEBIAN_FRONTEND=noninteractive apt install -y ffmpeg python3-pip
RUN apt update && apt install -y ffmpeg python3-pip git nvidia-cuda-toolkit

# Get username from commandline
ARG username
ARG uid

RUN ls 
RUN pip install --upgrade pip
RUN pip install git+https://github.com/m-bain/whisperx.git

WORKDIR /cc/whisper
RUN mkdir /cache && chown $uid /cache && chown $uid /cc/whisper

COPY requirements.txt requirements.txt

ENV NUMBA_CACHE_DIR=/tmp/ \
    PATH="${PATH}:/cc/cryocore/bin:/cc/cryocloud/bin:/miniconda3/bin" \
    CC_DIR="/cc/cryocloud/" \
    PYTHONPATH="${PYTHONPATH}:/cc/cryocore:/cc/cryocloud:." \
    PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:24 \
    TRANSFORMERS_CACHE=/cc/whisper/.cache/huggingface/hub \
    MPLCONFIGDIR=/cc/whisper/.cache/matplotlib \
    HF_HOME=/cc/whisper \
    HOME=/cc/whisper

# This makes issues
# RUN pip uninstall -y transformer-engine

#RUN pip install -q git+https://github.com/huggingface/transformers
#RUN pip install -q accelerate optimum
#RUN pip install -q ipython-autotime
RUN pip install Cython


# Set username
RUN adduser --disabled-password --uid $uid $username
RUN chown -R $username /cc
USER $username

ENV PATH="/cc/whisper/.local/bin:${PATH}"

RUN pip install -r requirements.txt
RUN pip install pip install --upgrade torch torchvision

# Add docker version of CryoCore
RUN cd /tmp; git clone https://github.com/Snarkdoof/cryocore.git; cp -r cryocore/dockercc /cc/cryocore

# Add CryoCloud
RUN cd /cc; git clone https://github.com/Snarkdoof/cryocloud.git; cd cryocloud; git checkout develop

# Build: sudo docker build --build-arg username=$USER --build-arg uid=$UID -t whisper .
# Run: sudo docker run -v <yourcachedir>:/cc/whisper/.cache --gpus all --rm -u $UID --it whisper


