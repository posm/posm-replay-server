FROM ubuntu:18.04

MAINTAINER togglecorp info@togglecorp.com

ENV PYTHONUNBUFFERED 1
ENV PYTHON3 /usr/local/bin/python3
ENV PIP3 /usr/local/bin/pip3

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

# Update and install common packages with apt
RUN apt-get update -y && apt-get install -y \
        # Basic Packages
        git \
        locales \
        vim \
        curl \
        gnupg \
        apt-transport-https \
        ca-certificates \
        cron \
        unzip \
        python3 \
        python3-dev \
        python3-setuptools \
        python3-pip \
        # For osmium
        libosmium2-dev libprotozero-dev rapidjson-dev libboost-program-options-dev \
        libbz2-dev zlib1g-dev libexpat1-dev cmake pandoc \
    && pip3 install -r requirements.txt

COPY . /code/

# CMD ./deploy/scripts/prod_exec.sh
