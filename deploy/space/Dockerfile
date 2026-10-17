FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY design ./design
COPY start.sh ./
RUN mkdir -p data models && chown -R user /home/user/app
USER user
ENV GOOGLE_APPLICATION_CREDENTIALS=/tmp/sa.json PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["sh", "start.sh"]
