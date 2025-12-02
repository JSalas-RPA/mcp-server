FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias primero (mejor práctica)
COPY requirements.txt .
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto después
COPY . .

# Exponer el puerto (esto es solo documentación)
EXPOSE 8080

# Usar gunicorn si es una app web (recomendado para producción)
# Asegúrate de tener gunicorn en requirements.txt 
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "server:app"]