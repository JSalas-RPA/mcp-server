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

# Opción 2: Ejecutar el script directamente (Más simple, pero menos robusto)
CMD ["python", "server.py"]