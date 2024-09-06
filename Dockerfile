# Based on:
# https://stackoverflow.com/questions/68673221/warning-running-pip-as-the-root-user
# https://www.thegeekdiary.com/run-docker-as-a-non-root-user/

FROM nvcr.io/nvidia/pytorch:24.01-py3

# FROM nvcr.io/nvidia/nemo:24.07  # over 28 gigs...

RUN apt update && echo "8\n30\n8\n" | DEBIAN_FRONTEND=noninteractive apt install -y ffmpeg
RUN apt-get install -y libsndfile1 ffmpeg

# Get username from commandline
ARG username
ARG uid
ARG HFTOKEN

#RUN git clone https://github.com/NVIDIA/TransformerEngine.git && \
#    cd TransformerEngine && \
#    git fetch origin 8c9abbb80dba196f086b8b602a7cf1bce0040a6a && \
#    git checkout FETCH_HEAD && \
#    git submodule init && git submodule update && \
#    MAKEFLAGS="-j 2" NVTE_FRAMEWORK=pytorch NVTE_WITH_USERBUFFERS=1 MPI_HOME=/usr/local/mpi pip install .

RUN ls 
RUN pip install --upgrade pip
# RUN pip install transformer_engine

# RUN pip install git+https://github.com/m-bain/whisperx.git

WORKDIR /jojo/
RUN mkdir /cache && chown $uid /cache && chown $uid /jojo

COPY requirements.txt requirements.txt

ENV NUMBA_CACHE_DIR=/tmp/ \
    PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:24 \
    MPLCONFIGDIR=/jojo/.cache/matplotlib \
    HF_HOME=/jojo \
    HOME=/jojo

# This makes issues
RUN pip uninstall -y transformer-engine
#RUN apt install -y libcublas11


ENV PATH="/jojo/.local/bin:${PATH}"

RUN mkdir -p ~/.config 
COPY pip.conf ~/.config/pip

RUN pip3 install -r requirements.txt

RUN pip install Cython && pip install nemo_toolkit['all']

RUN pip install pyannote.audio

# RUN pip install --upgrade torch torchvision


# Add the local files here
COPY . /jojo/

RUN pip3 install -r /jojo/whisperX/requirements.txt
RUN pip install --upgrade torchvision

RUN pip install schiblib
# RUN cd /jojo/schiblib && pip install .  && cd /jojo
RUN cd /jojo/whisperX && pip install .  && cd /jojo

# Add simplified CryoCore
RUN apt update && echo "Etc/UTC" > /etc/timezone && \
    echo 8 | DEBIAN_FRONTEND=noninteractive apt install -y sudo tzdata mysql-server mysql-client && \
    cd /jojo; git clone https://github.com/Snarkdoof/cryocore.git && \
    cd /jojo/cryocore # && \
    service mysql start && \
    echo y | ./CryoCore/Install/install.sh

# Add CryoCloud
RUN pip install mysql-connector-python

RUN cd /jojo; git clone https://github.com/Snarkdoof/cryocloud.git; cd cryocloud; git checkout develop

ENV CC_DIR="/jojo/cryocloud/" \
    PATH="${PATH}:/jojo/cryocore/bin:/jojo/cryocloud/bin:/miniconda3/bin" \
    PYTHONPATH="${PYTHONPATH}:/jojo/cryocore:/jojo/cryocloud:."

# Set username
RUN adduser --disabled-password --uid $uid $username
RUN chown -R $username /jojo
# USER $username

# Build: sudo docker build --build-arg username=$USER --build-arg uid=$UID -t whisper .
# Run: sudo docker run -v <yourcachedir>:/jojo/.cache --gpus all --rm -u $UID --it whisper
