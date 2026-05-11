FROM python:3.13-slim

COPY . /code

RUN pip install --no-cache-dir httpx pandas numpy python-dateutil spacy
RUN python -m spacy download fr_core_news_md

