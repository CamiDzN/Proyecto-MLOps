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

# Nombre con que se registró el modelo en MLflow (tal como en tu DAG: "RealtorPriceModel")
MODEL_NAME = os.getenv("MODEL_NAME", "RealtorPriceModel")

# URI del Tracking Server de MLflow (p.ej.: http://10.43.101.196:30003)
# Cambié el valor por defecto a la URL que nos indicaste en MLflow
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://10.43.101.196:30003")

# Cadena de conexión a la base de datos RAW_DATA (PostgreSQL)
# Debe existir la tabla `raw_data` con columnas:
#   id (serial), input (jsonb/text), prediction (float), model_version (text o int), timestamp (timestamp)
DB_URL = os.getenv("DB_URL", "postgresql://user:pass@db:5432/raw_data")

# Crea la instancia de FastAPI
app = FastAPI(title="RealtorPriceModel Inference API")

# ──────────────────────────────────────────────────────
# 2) CARGA DEL MODELO DESDE MLflow
# ──────────────────────────────────────────────────────

try:
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    # Obtiene las versiones en stage “Production” para el modelo
    prod_versions = client.get_latest_versions(name=MODEL_NAME, stages=["Production"])
    if not prod_versions:
        raise RuntimeError(f"No existe ninguna versión en Production para el modelo '{MODEL_NAME}'.")
    model_version = prod_versions[0].version  # la versión que está en Production
    # Carga el modelo completo (artifact) desde el registry “models:/…”
    model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/Production")
except Exception as e:
    # Si falla la carga del modelo, detenemos la aplicación con un error claro
    raise RuntimeError(f"Error al conectar con MLflow o al cargar modelo: {e}")

# ──────────────────────────────────────────────────────
# 3) CONEXIÓN A LA BASE DE DATOS RAW_DATA
# ──────────────────────────────────────────────────────

try:
    engine = create_engine(DB_URL, pool_pre_ping=True)
except SQLAlchemyError as e:
    raise RuntimeError(f"Error al conectar con la base de datos RAW_DATA: {e}")

# ──────────────────────────────────────────────────────
# 4) MÉTRICAS DE PROMETHEUS
# ──────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "api_request_count", "Número de peticiones al endpoint /predict", ["model_name"]
)
REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds", "Latencia de petición /predict (segundos)", ["model_name"]
)


# ──────────────────────────────────────────────────────
# 5) DEFINICIÓN DEL ESQUEMA DE ENTRADA
# ──────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    """
    Estructura del JSON para POST /predict:

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
    Recibe un JSON con los features de una vivienda y devuelve la predicción
    y la versión de modelo usada, además de almacenar en DB RAW_DATA.
    """
    # 1) Métricas: incrementa contador de solicitudes
    REQUEST_COUNT.labels(model_name=MODEL_NAME).inc()

    # 2) Prepara un DataFrame con los features (un solo registro)
    features_dict = request.data
    try:
        df_features = pd.DataFrame([features_dict])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al formar DataFrame de entrada: {e}")

    # 3) Invoca el modelo para predecir
    try:
        with REQUEST_LATENCY.labels(model_name=MODEL_NAME).time():
            prediction_array = model.predict(df_features)
            # model.predict(...) puede devolver lista o numpy array; tomamos el primer valor
            pred_value = float(prediction_array[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al invocar modelo: {e}")

    # 4) Guarda en la base de datos RAW_DATA
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
                    "ver": str(model_version)
                }
            )
    except SQLAlchemyError as e:
        # No abortamos la predicción por completo si falla el registro en la tabla;
        # devolvemos la inferencia pero avisamos en logs.
        print(f"[ERROR] No se pudo guardar en DB RAW_DATA: {e}")

    # 5) Retorna la respuesta JSON
    return {"prediction": pred_value, "model_version": model_version}


# ──────────────────────────────────────────────────────
# 7) ENDPOINT /metrics (Prometheus)
# ──────────────────────────────────────────────────────

@app.get("/metrics")
def metrics():
    """
    Prometheus client endpoint. Devuelve métricas en formato text/plain.
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ──────────────────────────────────────────────────────
# 8) ROOT (opcional) – prueba básica
# ──────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "RealtorPriceModel Inference API",
        "model_name": MODEL_NAME,
        "model_version": model_version,
        "mlflow_tracking_uri": MLFLOW_TRACKING_URI,
    }
