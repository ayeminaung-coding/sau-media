FROM python:3.12-slim

# ffmpeg performs the per-platform transcodes. The API and worker services
# share this image so a worker can be scaled out independently later.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY sau ./sau
COPY scripts ./scripts

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "sau.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
