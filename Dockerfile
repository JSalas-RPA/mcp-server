# Usamos Python slim para que sea liviano
FROM python:3.13-slim

# Directorio de trabajo
WORKDIR /app

# Copiar e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

EXPOSE 7000

# Ejecutar servidor MCP
CMD ["python", "server.py"]
