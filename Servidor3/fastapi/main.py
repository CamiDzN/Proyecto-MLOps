# fastapi/main.py

import os
import json
import pandas as pd

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict

from mlflow.tracking import MlflowClient
import mlflow.pyfunc

from sqlalchemy import create_engine

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

###############################################################################
# 1) Variables de entorno utilizadas por el servicio
#
#    Puedes modificar estas en tu Deployment de Kubernetes:
#      - MODEL_NAME: nombre del modelo en MLflow (etiqueta “Registered Model”)
#      - MLFLOW_TRACKING_URI: URL donde corre tu servidor MLflow (http://mlflow:5000 si en k8s Service se llama "mlflow")
#      - DB_URL: cadena de conexión a la base de datos PostgreSQL que contiene la tabla "raw_data"
#
###############################################################################

MODEL_NAME          = os.getenv("MODEL_NAME", "MiModelo")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-server:5000")
DB_URL              = os.getenv("DB_URL", "postgresql://user:pass@db:5432/raw_data")

###############################################################################
# 2) Instancia FastAPI y definimos métricas para Prometheus
###############################################################################

app = FastAPI(
    title="FastAPI Inferencia Realtor",
    description=(
        "Servicio de inferencia que carga el modelo en producción desde MLflow y "
        "registra cada predicción en la tabla raw_data de PostgreSQL. "
        "Expone métricas Prometheus en /metrics."
    ),
    version="1.0.0"
)

# Métricas:
REQUEST_COUNT = Counter(
    "api_request_count",
    "Número de peticiones al endpoint /predict",
    ["model"]
)
REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds",
    "Latencia de ejecución del endpoint /predict (en segundos)",
    ["model"]
)

###############################################################################
# 3) Definición del esquema de datos de entrada (Pydantic)
###############################################################################

class PredictRequest(BaseModel):
    """
    Estructura del JSON de entrada para /predict:
    {
        "data": {
            "bed": 3,
            "bath": 2,
            "acre lot": 0.5,
            "house size": 1500
            
        }
    }
    """
    data: Dict[str, float]

###############################################################################
# 4) Variables globales para el modelo y la conexión a la base de datos
#
#    Estas se inicializarán en el evento 'startup'
###############################################################################

model = None            # objeto mlflow.pyfunc pyfunc model cargado en memoria
model_version = None    # versión de modelo en producción (e.g. "3")
engine = None           # objeto SQLAlchemy Engine para la base de datos raw_data

###############################################################################
# 5) Evento de startup de FastAPI: cargar modelo y conectar a BD
###############################################################################

@app.on_event("startup")
def load_model_and_db():
    global model, model_version, engine

    # 5.1) Conectar a MLflow y obtener la última versión en stage "Production"
    try:
        client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
        prod_models = client.get_latest_versions(MODEL_NAME, stages=["Production"])
        if not prod_models:
            raise RuntimeError(
                f"No hay ningún modelo en stage 'Production' para '{MODEL_NAME}'"
            )
        # Tomamos el primer elemento (el más reciente en Production)
        mv = prod_models[0]
        model_version = mv.version

        # Cargar el modelo en memoria
        model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/Production")
        print(f"Modelo '{MODEL_NAME}' versión {model_version} cargado desde MLflow.")

    except Exception as e:
        print(f"Error al cargar modelo desde MLflow: {e}")
        # Abortamos la aplicación: sin modelo en producción no continuamos
        raise

    # 5.2) Crear la conexión a PostgreSQL (BD raw_data)
    try:
        engine = create_engine(DB_URL)
        # Probar la conexión rápidamente
        with engine.connect() as conn:
            conn.execute("SELECT 1;")
        print(f"Conexión exitosa a la base de datos RAW_DATA [{DB_URL}].")

    except Exception as e:
        print(f"Error al conectar a la BD RAW_DATA: {e}")
        raise

###############################################################################
# 6) Endpoint /predict
###############################################################################

@app.post("/predict")
def predict(req: PredictRequest):
    """
    Endpoint que recibe un JSON con clave "data" (diccionario de características),
    realiza la predicción utilizando el modelo en producción, registra el resultado
    en la tabla raw_data y devuelve la predicción y la versión de modelo.

    Ejemplo de llamada:
      POST /predict
      {
        "data": {
          "bed": 3,
          "bath": 2,
          "acre lot": 0.5,
          "house size": 1500
        }
      }

    Respuesta:
      {
        "prediction": 245000.0,
        "model_version": "3"
      }
    """
    # 6.1) Incrementar contador de peticiones para este modelo
    REQUEST_COUNT.labels(model=MODEL_NAME).inc()

    try:
        # 6.2) Construir DataFrame a partir del diccionario recibido
        df_input = pd.DataFrame([req.data])

        # 6.3) Medir latencia de inferencia y hacer la predicción
        with REQUEST_LATENCY.labels(model=MODEL_NAME).time():
            prediction_array = model.predict(df_input)
            # Suponemos que predict retorna un array unidimensional
            pred = float(prediction_array[0])

        # 6.4) Insertar registro en tabla raw_data:
        #      columnas: input (TEXT), prediction (FLOAT), model_version (TEXT), timestamp (TIMESTAMP)
        with engine.begin() as conn:
            conn.execute(
                """
                INSERT INTO raw_data (input, prediction, model_version, timestamp)
                VALUES (:input, :pred, :ver, now());
                """,
                {
                    "input": json.dumps(req.data, ensure_ascii=False),
                    "pred": pred,
                    "ver": str(model_version)
                }
            )

        # 6.5) Devolver JSON con predicción y versión
        return {
            "prediction": pred,
            "model_version": model_version
        }

    except Exception as e:
        # Ante cualquier error, devolvemos 500 con detalle
        raise HTTPException(status_code=500, detail=f"Error en /predict: {e}")

###############################################################################
# 7) Endpoint /metrics para que Prometheus rastree métricas
###############################################################################

@app.get("/metrics")
def metrics():
    """
    Devuelve las métricas de Prometheus generadas en memoria
    (Counters y Histograms) para ser "scrapeadas".
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
