FROM python:3.11-slim

# torch 등 빌드에 필요한 최소 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.27" python-multipart

COPY . .
EXPOSE 8001
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8001"]
