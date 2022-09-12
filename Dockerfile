# sudo docker build . -t aiohttp_image
# sudo docker run --rm --name aiohttp_container -p 8082:8082 aiohttp_image
# sudo docker push 116589935960.dkr.ecr.eu-west-1.amazonaws.com/aiohttp_image:latest

FROM python:3.8-slim

RUN apt-get clean && apt-get -y update
RUN apt-get -y install python3-dev build-essential
RUN apt-get -y install libssl-dev
RUN apt-get -y install redis

COPY . .

RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

EXPOSE 8082

CMD ["python", "./app.py"]