FROM python:3.13.3-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
ENV PORT=8080
CMD sh -c "gunicorn 'zora.api:create_app()' --bind 0.0.0.0:$PORT --workers 2 --timeout 60"
