FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu
COPY app ./app
COPY scripts ./scripts
COPY models ./models
# веса CLIP запекаются в образ -> в рантайме интернет не нужен (требование переносимости)
RUN python scripts/download_models.py
ENV HF_HUB_OFFLINE=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
