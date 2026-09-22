FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY email_parser/requirements.txt /app/email_parser/requirements.txt
RUN pip install --no-cache-dir -r /app/email_parser/requirements.txt

COPY email_parser /app/email_parser

ENV PYTHONPATH=/app
ENTRYPOINT ["python", "-m", "email_parser"]
