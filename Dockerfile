# Container definition for deploying Data Mosaic to Cloud Run.

FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (separate layer, so this only re-runs
# when requirements.txt actually changes — faster rebuilds).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application.
COPY . .

# Cloud Run injects the actual port to listen on via $PORT — never
# hardcode 8080 here, always read the env var.
ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
