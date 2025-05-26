import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict
from mlflow.tracking import MlflowClient
import mlflow.pyfunc
import pandas as pd
from sqlalchemy import create_engine
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

# Parámetros vía ENV (puedes ajustarlos en tu Deployment)
MODEL_NAME = os.getenv("MODEL_NAME", "MiModelo")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-server:5000")
DB_URL = os.getenv("DB_URL", "postgresql://user:pass@db:5432/raw_data")

app = FastAPI()

# Conexión a MLflow: busca siempre el último modelo en stage=Production
client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
prod = client.get_latest_versions(MODEL_NAME, stages=["Production"])
if not prod:
    raise RuntimeError(f"No hay modelo en Production para {MODEL_NAME}")
model_version = prod[0].version
model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/Production")

# Conexión a la BD de RAW DATA
engine = create_engine(DB_URL)

# Métricas para Prometheus
REQUEST_COUNT = Counter("api_request_count", "Número de peticiones /predict", ["model"])
REQUEST_LATENCY = Histogram("api_request_latency_seconds", "Latencia de /predict", ["model"])

class PredictRequest(BaseModel):
    data: Dict[str, float]

@app.post("/predict")
def predict(req: PredictRequest):
    REQUEST_COUNT.labels(model=MODEL_NAME).inc()
    with REQUEST_LATENCY.labels(model=MODEL_NAME).time():
        df = pd.DataFrame([req.data])
        pred = float(model.predict(df)[0])
        # Guardar en RAW DATA
        with engine.begin() as conn:
            conn.execute(
                "INSERT INTO raw_data (input, prediction, model_version, timestamp) "
                "VALUES (:input, :pred, :ver, now())",
                {
                    "input": json.dumps(req.data),
                    "pred": pred,
                    "ver": model_version
                }
            )
    return {"prediction": pred, "model_version": model_version}

@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
