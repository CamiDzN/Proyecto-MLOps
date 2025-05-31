# 1. Imagen base ligera de Python
FROM python:3.10-slim

# 2. Fijamos el directorio de trabajo
WORKDIR /app

# 3. Copiamos requirements.txt e instalamos dependencias de sistema si las necesitamos
COPY requirements.txt /app/requirements.txt

# 4. Instalamos dependencias del sistema necesarias para compilar algunas librerías
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# 5. Instalamos las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiamos el código de la aplicación
COPY main.py /app/main.py

# 7. Exponemos el puerto en el que correrá FastAPI
EXPOSE 8000

# 8. Comando para ejecutar Uvicorn al iniciar el contenedor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
