import os
import json
import datetime
import pandas as pd
import mlflow
import mlflow.pyfunc
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, validator, Field
from typing import Literal
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ─────────────────────────────────────────────────────────────────────────────
# 1) PARÁMETROS Y CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

# Nombre del modelo en MLflow Registry (coincide con tu DAG)
MODEL_NAME = os.getenv("MODEL_NAME", "RealtorPriceModel")

# URI del Tracking Server de MLflow dentro del clúster (servicio mlflow-service en namespace mlops, puerto 5000)
# <-- ojo: aquí usamos el nombre DNS dentro de Kubernetes: mlflow-service.mlops.svc.cluster.local:5000
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    "http://mlflow-service.mlops.svc.cluster.local:5000"
)

# Cadena de conexión a PostgreSQL (servicio postgres-service en namespace mlops, db 'mlflow')
# Asegúrate de que exista:
#   CREATE TABLE raw_data (
#     id SERIAL PRIMARY KEY,
#     input JSONB,
#     prediction DOUBLE PRECISION,
#     model_version TEXT,
#     timestamp TIMESTAMP WITHOUT TIME ZONE
#   );
DB_URL = os.getenv(
    "DB_URL",
    "postgresql://postgres:supersecret@postgres-service.mlops.svc.cluster.local:5432/mlflow"
)

app = FastAPI(
    title="RealtorPriceModel Inference API",
    version="1.0",
    description=(
        "Carga el modelo ‘RealtorPriceModel’ desde MLflow Registry (Production),\n"
        "recibe un JSON plano con features, devuelve el precio estimado,\n"
        "y guarda cada inferencia en la tabla raw_data de PostgreSQL.\n"
        "También expone /metrics para Prometheus."
    )
)

loaded_model = None        # se inicializará en startup
model_version = None       # para exponer en /


# ─────────────────────────────────────────────────────────────────────────────
# 2) EVENTO de STARTUP: CARGAR el modelo desde MLflow Registry
# ─────────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def load_model_on_startup():
    """
    Cada vez que arranca un worker de FastAPI, conecta a MLflow Tracking Server
    y carga la versión que esté en ‘Production’ para MODEL_NAME.
    """
    global loaded_model, model_version

    try:
        # 2.1) Apunta a tu MLflow interno en Kubernetes
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

        # 2.2) Directamente usamos la sintaxis "models:/RealtorPriceModel/Production"
        model_uri = f"models:/{MODEL_NAME}/Production"
        loaded_model = mlflow.pyfunc.load_model(model_uri)

        # En MlflowClient podríamos extraer la versión numérica para mostrarla en "/"
        client = mlflow.tracking.MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
        prod_versions = client.get_latest_versions(name=MODEL_NAME, stages=["Production"])
        if not prod_versions:
            raise RuntimeError(f"No hay versiones en Production para '{MODEL_NAME}'")
        model_version = prod_versions[0].version  # ej. "3", "4", etc.

        print(f"[startup] ✅ Modelo cargado: {model_uri}  (versión {model_version})")
    except Exception as e:
        print(f"[startup] ❌ Error al cargar el modelo: {e}")
        # Dejamos loaded_model = None para que /predict dé error si se llama
        loaded_model = None
        model_version = None


# ─────────────────────────────────────────────────────────────────────────────
# 3) CONEXIÓN A PostgreSQL para guardar raw_data
# ─────────────────────────────────────────────────────────────────────────────
try:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    # No hacemos ningún acceso inmediato; solo abrimos el engine para usar más tarde.
except SQLAlchemyError as e:
    raise RuntimeError(f"[startup] ❌ Error al conectar con PostgreSQL (raw_data): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 4) MÉTRICAS PARA PROMETHEUS
# ─────────────────────────────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "api_request_count",
    "Número total de peticiones al endpoint /predict",
    ["model_name"]
)
REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds",
    "Latencia (segundos) en /predict",
    ["model_name"]
)


# ─────────────────────────────────────────────────────────────────────────────
# 5) ESCHEMA DE ENTRADA PARA /predict
# ─────────────────────────────────────────────────────────────────────────────
class PredictRequest(BaseModel):
    """
    JSON plano con las 6 features (tal como entrenó el DAG):
    {
      "bed": 3.0,
      "bath": 2.5,
      "acre_lot": 0.8,
      "house_size": 1800.0,
      "prev_sold_date": "2023-11-15",
      "status": "for_sale"
    }
    """
    bed: float = Field(..., description="Número de recámaras (ej. 3.0)")
    bath: float = Field(..., description="Número de baños (ej. 2.5)")
    acre_lot: float = Field(..., description="Tamaño del lote en acres (ej. 0.8)")
    house_size: float = Field(..., description="Área de la casa en pies² (ej. 1800)")
    prev_sold_date: str = Field(
        ...,
        description="Fecha de última venta en formato YYYY-MM-DD (ej. 2023-11-15)"
    )
    status: Literal["for_sale", "to_build"] = Field(
        ...,
        description="Estado: 'for_sale' o 'to_build'"
    )

    @validator("prev_sold_date")
    def validar_formato_fecha(cls, v):
        """
        Verifica que prev_sold_date venga en formato YYYY-MM-DD y sea parseable.
        """
        try:
            datetime.datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("prev_sold_date debe tener formato YYYY-MM-DD")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# 6) ENDPOINT: /
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    """
    Devuelve información básica de la API y la versión de modelo que está en memoria.
    """
    return {
        "service": "RealtorPriceModel Inference API",
        "model_name": MODEL_NAME,
        "model_version": model_version,
        "mlflow_tracking_uri": MLFLOW_TRACKING_URI
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7) ENDPOINT: /predict
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/predict")
def predict(request: PredictRequest):
    """
    Recibe un JSON con las 6 features, aplica preprocesamiento idéntico al DAG
    (cálculo de days_since_last_sale + one-hot de status), invoca loaded_model.predict(),
    guarda la inferencia en raw_data (PostgreSQL) y devuelve {"prediction": X, "model_version": Y}.
    """
    global loaded_model, model_version

    # 7.1) Verificar que el modelo está cargado
    if loaded_model is None:
        raise HTTPException(
            status_code=500,
            detail="No hay ningún modelo cargado en memoria. Intenta reiniciar la API o revisar logs."
        )

    # 7.2) Convertir el Pydantic model a un DataFrame de pandas (1 fila)
    data_in = request.dict()
    df = pd.DataFrame([data_in])

    # 7.3) Preprocesamiento (tal cual en tu DAG de Airflow):
    #      - Convertir prev_sold_date a datetime (tz-naive)
    #      - Calcular days_since_last_sale = (UTC now - prev_sold_date).days
    #      - One-hot encode de status (drop_first -> solo 'status_to_build')
    try:
        df["prev_sold_date"] = pd.to_datetime(df["prev_sold_date"], format="%Y-%m-%d", errors="coerce")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Formato inválido en prev_sold_date: {e}")

    now_utc = datetime.datetime.utcnow()
    df["days_since_last_sale"] = (
        (now_utc - df["prev_sold_date"]).dt.days.fillna(-1).astype(int)
    )

    df["status_to_build"] = df["status"].apply(lambda x: 1 if x == "to_build" else 0)

    # 7.4) Seleccionar exactamente las columnas en el orden que entrenó el DAG:
    feature_cols = [
        "bed",
        "bath",
        "acre_lot",
        "house_size",
        "days_since_last_sale",
        "status_to_build"
    ]
    missing_cols = set(feature_cols) - set(df.columns)
    if missing_cols:
        raise HTTPException(status_code=400, detail=f"Faltan columnas: {missing_cols}")

    X = df[feature_cols]

    # 7.5) Invocar al modelo y medir latencia para Prometheus
    REQUEST_COUNT.labels(model_name=MODEL_NAME).inc()
    try:
        with REQUEST_LATENCY.labels(model_name=MODEL_NAME).time():
            pred_arr = loaded_model.predict(X)
            prediction_value = float(pred_arr[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error llamando al modelo: {e}")

    # 7.6) Guardar en la tabla raw_data de PostgreSQL
    insert_sql = text("""
        INSERT INTO raw_data (input, prediction, model_version, timestamp)
        VALUES (:input_json, :pred, :ver, now())
    """)
    try:
        with engine.begin() as conn:
            conn.execute(
                insert_sql,
                {
                    "input_json": json.dumps(data_in),
                    "pred": prediction_value,
                    "ver": str(model_version)
                }
            )
    except SQLAlchemyError as e:
        # Solo avisamos en logs, pero no abortamos la inferencia.
        print(f"[WARN] No se pudo guardar en raw_data: {e}")

    # 7.7) Devolver al cliente
    return {
        "prediction": prediction_value,
        "model_version": str(model_version)
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8) ENDPOINT: /metrics (para Prometheus)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/metrics")
def metrics():
    """
    Devuelve las métricas en formato Prometheus (text/plain) para que Prometheus haga scrape.
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
