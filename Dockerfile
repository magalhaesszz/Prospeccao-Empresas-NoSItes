FROM python:3.11-slim

# Chromium + ChromeDriver via apt (Railway/Debian)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Variáveis padrão para produção
ENV HEADLESS=true
ENV USAR_UNDETECTED=false

EXPOSE 8080

CMD ["python", "app.py"]
