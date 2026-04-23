FROM python:3.13.3-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn "zora.api:create_app()" --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 60
