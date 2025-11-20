# Imagen base
FROM python:3.11-slim

# Directorio de trabajo
WORKDIR /app

# Copiar archivos del proyecto
COPY . .

# Instalar dependencias del sistema (para PDFs)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 7000

# Comando de inicio
CMD ["python", "server.py"]
