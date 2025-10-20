FROM python:3.13
RUN apt update && apt install xmlsec1 redis -y
ENV PYTHONUNBUFFERED=1
WORKDIR /code
#RUN bash .docker/scripts/setup-sass.sh
COPY ./requirements-dev.txt /code/
RUN pip install -r requirements-dev.txt
#COPY . /code/
