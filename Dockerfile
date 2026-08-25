FROM astral/uv:python3.13-bookworm-slim

WORKDIR /code

# Keep the venv outside /code: compose bind-mounts the source tree over /code
# at runtime, which would otherwise shadow a venv living inside it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Same reasoning for the model data: /code is replaced by the bind mount.
ENV PIPER_VOICE_DIR=/opt/piper-voices
ENV HF_HOME=/opt/huggingface

COPY pyproject.toml uv.lock ./
RUN uv sync --locked
RUN uv run python -m spacy download fr_core_news_md
RUN uv run python -m piper.download_voices \
        --download-dir "$PIPER_VOICE_DIR" fr_FR-siwis-medium
# Bake the translation model in so review-time builds never re-download it.
RUN uv run python -c "\
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM; \
m='Helsinki-NLP/opus-mt-fr-en'; \
AutoTokenizer.from_pretrained(m); AutoModelForSeq2SeqLM.from_pretrained(m)"

COPY . .
