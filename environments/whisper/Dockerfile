# Based on:
# https://stackoverflow.com/questions/68673221/warning-running-pip-as-the-root-user
# https://www.thegeekdiary.com/run-docker-as-a-non-root-user/

FROM nvcr.io/nvidia/pytorch:22.01-py3

run apt update && echo "8\n30\n8\n" | DEBIAN_FRONTEND=noninteractive apt install -y ffmpeg

# Get username from commandline
ARG username
ARG uid

RUN ls 
RUN pip3 install --upgrade pip

RUN apt update && apt install -y python3-tk libnvinfer8
WORKDIR /cc/whisper
RUN mkdir /cache && chown $uid /cache && chown $uid /cc/whisper

COPY requirements.txt requirements.txt
#COPY whisper whisper
#COPY whisper-timestamped whisper

# Get the repositories
# RUN git clone https://github.com/linto-ai/whisper-timestamped.git whisper
# RUN cd whisper; python3 setup.py install

ENV NUMBA_CACHE_DIR=/tmp/ \
    PATH="${PATH}:/cc/cryocore/bin:/cc/cryocloud/bin:/miniconda3/bin" \
    CC_DIR="/cc/cryocloud/" \
    PYTHONPATH="${PYTHONPATH}:/cc/cryocore:/cc/cryocloud:." \
    PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:24 \
    TRANSFORMERS_CACHE=/cache/huggingface/hub \
    MPLCONFIGDIR=/cc/whisper/.cache/matplotlib \
    HF_HOME=/cc/whisper \
    HOME=/cc/whisper

# Set username
RUN adduser --disabled-password --uid $uid $username
RUN chown -R $username /cc
USER $username

ENV PATH="/cc/whisper/.local/bin:${PATH}"

RUN pip3 install -r requirements.txt

RUN pip3 install git+https://github.com/linto-ai/whisper-timestamped

# Add docker version of CryoCloud
RUN cd /tmp; git clone https://github.com/Snarkdoof/cryocore.git; cp -r cryocore/dockercc /cc/cryocore

# Add CryoCloud
RUN cd /cc; git clone https://github.com/Snarkdoof/cryocloud.git; cd cryocloud; git checkout develop

# Build: sudo docker build --build-arg username=$USER --build-arg uid=$UID -t whisper .
# Run: sudo docker run --gpus all --rm --it whisper
