FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scanner.py .

# State file persisted via volume mount
VOLUME /app/data
ENV SCANNER_STATE_FILE=/app/data/scanner_state.json

# Default: run scan
CMD ["python", "scanner.py"]
