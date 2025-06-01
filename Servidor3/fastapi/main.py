from fastapi import FastAPI, Response
from pydantic import BaseModel
from datetime import datetime
import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
import os
import logging

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import create_engine

# ───── Prometheus Metrics ─────
PREDICTIONS = Counter("inference_requests_total", "Total de peticiones de inferencia")
LATENCIES = Histogram(
    "inference_request_latency_seconds",
    "Latencia de las peticiones (segundos)",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5]
)

# ───── Configuración por Entorno ─────
MLFLOW_URI   = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MODEL_NAME   = os.getenv("MLFLOW_MODEL_NAME", "RealtorPriceModel")
RAW_URI      = os.getenv("RAW_DATA_DB_URI")
S3_ENDPOINT  = os.getenv("MLFLOW_S3_ENDPOINT_URL")

mlflow.set_tracking_uri(MLFLOW_URI)
if S3_ENDPOINT:
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = S3_ENDPOINT

engine = create_engine(RAW_URI)
app = FastAPI()
logging.basicConfig(level=logging.INFO)

class RawFeatures(BaseModel):
    brokered_by: float
    status: str
    price: float
    bed: float
    bath: float
    acre_lot: float
    street: float
    city: str
    state: str
    zip_code: float
    house_size: float
    prev_sold_date: str

def preprocess_and_align(data: dict, model) -> pd.DataFrame:
    df = pd.DataFrame([data])
    
    # 1) Rellenar numéricos
    num_cols = ["bed", "bath", "acre_lot", "house_size", "price"]
    df[num_cols] = df[num_cols].ffill().fillna(0)

    # 2) Calcular days_since_last_sale
    df["prev_sold_date"] = pd.to_datetime(df["prev_sold_date"], errors="coerce")
    now = pd.Timestamp.utcnow().replace(tzinfo=None)
    df["days_since_last_sale"] = (now - df["prev_sold_date"]).dt.days.fillna(-1).astype(int)

    # 3) Generar columnas dummy posibles
    df["status_to_build"] = 1 if data["status"] == "to_build" else 0
    df["status_for_sale"] = 1 if data["status"] == "for_sale" else 0

    # 4) Eliminar columnas no utilizadas
    drop_cols = ["brokered_by", "street", "zip_code", "city", "state", "prev_sold_date", "status"]
    df.drop(columns=drop_cols, inplace=True, errors="ignore")

    # 5) Probar combinaciones posibles
    candidate_sets = [
        ["bed", "bath", "acre_lot", "house_size", "days_since_last_sale", "status_to_build"],
        ["bed", "bath", "acre_lot", "house_size", "days_since_last_sale", "status_for_sale"],
        ["bed", "bath", "acre_lot", "house_size", "days_since_last_sale"],
    ]

    for cols in candidate_sets:
        try:
            aligned = df.reindex(columns=cols, fill_value=0)
            # Validación rápida de predict
            model.predict(aligned)
            logging.info(f"Usando columnas para predicción: {cols}")
            return aligned
        except Exception as e:
            logging.warning(f"Falló intento con columnas {cols}: {str(e)}")
            continue

    raise ValueError("Ninguna combinación de columnas fue compatible con el modelo entrenado.")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/predict")
def predict(raw: RawFeatures):
    PREDICTIONS.inc()
    data_dict = raw.dict()
    now_utc = datetime.utcnow()
    logging.info(f"Solicitud de inferencia recibida: {data_dict}")

    with LATENCIES.time():
        model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/Production")
        df_input = preprocess_and_align(data_dict, model)
        prediction = model.predict(df_input)[0]
        logging.info(f"Predicción generada: {prediction}")

        client = MlflowClient()
        version = client.get_latest_versions(MODEL_NAME, stages=["Production"])[0].version

        record = {**data_dict, "fetched_at": now_utc}
        pd.DataFrame([record]).to_sql("realtor_raw", con=engine, if_exists="append", index=False)

    return {
        "prediction": prediction,
        "model_version": version
    }

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)