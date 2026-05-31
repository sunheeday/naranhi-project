FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
COPY backend/extractor-requirements.txt ./extractor-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r extractor-requirements.txt

COPY backend/app ./app
COPY backend/extractor ./extractor

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
