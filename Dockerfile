FROM python:3.10-alpine

WORKDIR /app

ADD dlq.py /app/
ADD pip-freeze.txt /app/

RUN pip install -r pip-freeze.txt --no-cache-dir

CMD [ "python", "dlq.py" ]
