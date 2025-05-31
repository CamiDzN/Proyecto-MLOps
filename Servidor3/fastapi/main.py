# main.py

import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict
from mlflow.tracking import MlflowClient
import mlflow.pyfunc
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

# ──────────────────────────────────────────────────────
# 1) PARÁMETROS Y CONFIGURACIÓN
# ──────────────────────────────────────────────────────

# Nombre del experimento/modelo en MLflow Registry (debe coincidir con lo que usó tu DAG)
MODEL_NAME = os.getenv("MODEL_NAME", "RealtorPriceModel")

# URI del Tracking Server de MLflow (por ejemplo: "http://mlflow-service:5000")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-service:5000")

# Cadena de conexión a la base de datos RAW_DATA (PostgreSQL). 
# Debe existir la tabla `raw_data` con columnas:
#   id (serial), input (jsonb o text), prediction (float), model_version (text), timestamp (timestamp)
DB_URL = os.getenv("DB_URL", "postgresql://user:pass@db:5432/raw_data")

# Creamos la app de FastAPI
app = FastAPI(title="RealtorPriceModel Inference API", version="1.0")

# ──────────────────────────────────────────────────────
# 2) CARGA DEL MODELO DESDE MLflow
# ──────────────────────────────────────────────────────

try:
    # 2.1) Conectamos al Tracking Server de MLflow
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    # 2.2) Obtenemos la lista de versiones en stage "Production" para nuestro modelo
    prod_versions = client.get_latest_versions(name=MODEL_NAME, stages=["Production"])
    if not prod_versions:
        raise RuntimeError(f"No existe ninguna versión en Production para el modelo '{MODEL_NAME}'.")
    # 2.3) Tomamos la primera (debería ser la más reciente/promovida)
    chosen_version = prod_versions[0]
    model_version = chosen_version.version      # ej. "5"
    run_id = chosen_version.run_id              # ej. "8b219909243f4ecc835e6baa0fe4b818"
    # 2.4) Con MLflowClient ya tenemos el run_id; ahora formamos la URI HTTP para descargar artefactos:
    #      MLflow permite acceder al modelo alojado en “artifacts” mediante:
    #         http://<MLFLOW_TRACKING_URI>/artifacts/<run_id>/model
    #      (donde “model” es el nombre que usaste en mlflow.sklearn.log_model(..., artifact_path="model", ...) )
    model_uri = f"{MLFLOW_TRACKING_URI}/artifacts/{run_id}/model"
    # 2.5) Cargamos el modelo en memoria usando mlflow.pyfunc
    model = mlflow.pyfunc.load_model(model_uri)
except Exception as e:
    # Si algo falló (no pudo conectar al Tracking Server, no encontró Production, etc.), detenemos la app.
    raise RuntimeError(f"Error al conectar con MLflow o al cargar el modelo: {e}")

# ──────────────────────────────────────────────────────
# 3) CONEXIÓN A LA BASE DE DATOS RAW_DATA (PostgreSQL)
# ──────────────────────────────────────────────────────

try:
    engine = create_engine(DB_URL, pool_pre_ping=True)
except SQLAlchemyError as e:
    raise RuntimeError(f"Error al conectar con la base de datos RAW_DATA: {e}")

# ──────────────────────────────────────────────────────
# 4) MÉTRICAS PARA PROMETHEUS
# ──────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "api_request_count", 
    "Número de peticiones al endpoint /predict", 
    ["model_name"]
)
REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds", 
    "Latencia de petición /predict (segundos)", 
    ["model_name"]
)

# ──────────────────────────────────────────────────────
# 5) ESQUEMA DE ENTRADA PARA /predict
# ──────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    """
    Estructura JSON que esperamos recibir en POST /predict:
    
    {
      "data": {
        "bed": 3,
        "bath": 2,
        "acre_lot": 0.5,
        "house_size": 1500,
        "status_for_sale": 1,
        "status_to_build": 0,
        "prev_sold_date": "2024-11-10T00:00:00Z",
        "price": 350000
      }
    }
    """
    data: Dict[str, float] = Field(
        ...,
        description="Diccionario con los features del inmueble, tal como el modelo fue entrenado."
    )

# ──────────────────────────────────────────────────────
# 6) ENDPOINT /predict
# ──────────────────────────────────────────────────────

@app.post("/predict")
def predict(request: PredictRequest):
    """
    Recibe un JSON con los features de una vivienda, realiza la inferencia
    con el modelo que está en MLflow (Production), guarda el request + prediction
    en la tabla raw_data (PostgreSQL) y devuelve el resultado.
    """
    # 6.1) Métricas: incrementamos el contador
    REQUEST_COUNT.labels(model_name=MODEL_NAME).inc()

    # 6.2) Transformamos el diccionario en un DataFrame de pandas (1 sola fila)
    features_dict = request.data
    try:
        df_features = pd.DataFrame([features_dict])
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Error al convertir a DataFrame de pandas: {e}"
        )

    # 6.3) Invocamos el modelo
    try:
        with REQUEST_LATENCY.labels(model_name=MODEL_NAME).time():
            prediction_array = model.predict(df_features)
            # model.predict(...) puede devolver una lista o array de numpy:
            pred_value = float(prediction_array[0])
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al invocar el modelo para inferencia: {e}"
        )

    # 6.4) Guardamos en la tabla raw_data (PostgreSQL)
    insert_sql = text("""
        INSERT INTO raw_data (input, prediction, model_version, timestamp)
        VALUES (:input_json, :pred, :ver, now())
    """)
    try:
        with engine.begin() as conn:
            conn.execute(
                insert_sql,
                {
                    "input_json": json.dumps(features_dict),
                    "pred": pred_value,
                    "ver": model_version
                }
            )
    except SQLAlchemyError as e:
        # Si falla el guardado en la DB, no abortamos la inferencia: devolvemos el resultado
        # pero imprimimos en logs para que sepas que no grabó en raw_data.
        print(f"[WARN] No se pudo guardar en raw_data: {e}")

    # 6.5) Devolvemos el JSON con la predicción y la versión de modelo usada
    return {
        "prediction": pred_value,
        "model_version": model_version
    }

# ──────────────────────────────────────────────────────
# 7) ENDPOINT /metrics (Prometheus)
# ──────────────────────────────────────────────────────

@app.get("/metrics")
def metrics():
    """
    Devuelve las métricas en formato text/plain para que Prometheus haga scrape.
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

# ──────────────────────────────────────────────────────
# 8) ROOT (opcional) – informa estado básico
# ──────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "RealtorPriceModel Inference API",
        "model_name": MODEL_NAME,
        "model_version": model_version,
        "mlflow_tracking_uri": MLFLOW_TRACKING_URI
    }
