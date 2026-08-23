FROM astral/uv:python3.13-bookworm-slim

WORKDIR /code

# Keep the venv outside /code: compose bind-mounts the source tree over /code
# at runtime, which would otherwise shadow a venv living inside it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock ./
RUN uv sync --locked
RUN uv run python -m spacy download fr_core_news_md

COPY . .
