# main.py

import os
import datetime
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
import mlflow.pyfunc
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

# -------------------------------------------------------
# 1. Configuración inicial
# -------------------------------------------------------

# Leer variables de entorno
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://10.43.101.196:30003")
MLFLOW_MODEL_NAME   = os.getenv("MLFLOW_MODEL_NAME", "RealtorPriceModel")
RAW_DATA_DB_URI     = os.getenv(
    "RAW_DATA_DB_URI",
    "mysql+pymysql://model_user:model_password@10.43.101.172:30306/RawData"
)

# Inicializar MLflow y cargar el modelo en producción
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
MODEL_URI = f"models:/{MLFLOW_MODEL_NAME}/Production"

try:
    model = mlflow.pyfunc.load_model(MODEL_URI)
    # Nota: el modelo debe haber sido registrado como "RealtorPriceModel" y tener al menos
    # una versión en el stage "Production".
except Exception as e:
    raise RuntimeError(f"Error cargando el modelo desde MLflow ({MODEL_URI}): {e}")

# Crear engine de SQLAlchemy para inserción en RAW DATA
try:
    engine_raw = create_engine(RAW_DATA_DB_URI)
    # Probar conexión
    with engine_raw.connect() as conn:
        conn.execute(text("SELECT 1"))
except Exception as e:
    raise RuntimeError(f"No se pudo conectar a la base de datos RAW_DATA ({RAW_DATA_DB_URI}): {e}")

# Inicializar FastAPI
app = FastAPI(
    title="RealtorPrice Inference API",
    description="API de inferencia para predicción de precios de viviendas, cargando el modelo en producción desde MLflow.",
    version="1.0.0",
)

# -------------------------------------------------------
# 2. Métricas de Prometheus
# -------------------------------------------------------

REQUEST_COUNT = Counter(
    "inference_requests_total",
    "Total de solicitudes de inferencia recibidas",
    ["endpoint", "http_status"]
)
REQUEST_LATENCY = Histogram(
    "inference_request_duration_seconds",
    "Latencia de las solicitudes de inferencia",
    ["endpoint"]
)

# -------------------------------------------------------
# 3. Esquema de entrada (Pydantic)
# -------------------------------------------------------

class HouseFeatures(BaseModel):
    """
    Campos esperados para una predicción de vivienda.
    Los nombres deben coincidir con los features usados en el entrenamiento,
    antes de pasar por la transformación (_prep) del DAG de Airflow.
    """
    status: str = Field(..., description="Estado: 'for_sale' o 'to_build'")
    bed: int = Field(..., ge=0, description="Número de habitaciones (integer ≥ 0)")
    bath: int = Field(..., ge=0, description="Número de baños (integer ≥ 0)")
    acre_lot: float = Field(..., gt=0, description="Tamaño del terreno en acres (float > 0)")
    house_size: float = Field(..., gt=0, description="Área de la casa en pies cuadrados (float > 0)")
    prev_sold_date: str = Field(
        ..., 
        description="Fecha de última venta en formato ISO (YYYY-MM-DD). Puede ser null o cadena vacía si no aplica."
    )

# -------------------------------------------------------
# 4. Función de preprocesamiento (mismo que en DAG de Airflow)
# -------------------------------------------------------

def preprocess_single(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica las mismas transformaciones definidas en el DAG de Airflow
    para cada registro de inferencia.
    - Relleno de nulos en numéricos
    - Cálculo de días desde última venta
    - One-hot de 'status'
    - Eliminación de columnas de alta cardinalidad
    - Colocar 'price' al final (aunque para inferencia no lo usamos)
    """
    # 1) Rellenar columnas numéricas (aunque en inferencia no hay nulos en numéricos salvo mala petición)
    num_cols = ["bed", "bath", "acre_lot", "house_size", "price"]
    for col in num_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    # 2) Calcular days_since_last_sale
    df["prev_sold_date"] = pd.to_datetime(df["prev_sold_date"], errors="coerce")
    now = datetime.datetime.utcnow()
    df["days_since_last_sale"] = (
        (now - df["prev_sold_date"]).dt.days.fillna(-1).astype(int)
    )

    # 3) One-hot encode de 'status' (drop_first=True)
    df = pd.get_dummies(df, columns=["status"], drop_first=True)

    # 4) Eliminar columnas irrelevantes o de alta cardinalidad
    drop_cols = [
        "brokered_by", "street", "zip_code", "city", "state",
        "prev_sold_date", "fetched_at"
    ]
    for c in drop_cols:
        if c in df.columns:
            df = df.drop(columns=[c])

    # 5) Asegurar que 'price' vaya al final (aunque no existe en entrada)
    if "price" in df.columns:
        cols = [c for c in df.columns if c != "price"] + ["price"]
        df = df[cols]

    return df

# -------------------------------------------------------
# 5. Endpoint /predict
# -------------------------------------------------------

@app.post("/predict")
def predict(input_data: HouseFeatures):
    start_time = datetime.datetime.utcnow()

    # ---------------------------------------------------
    # 5.1. Convertir entrada a DataFrame
    # ---------------------------------------------------
    try:
        # Construir DataFrame con una sola fila
        data = {
            "status": input_data.status,
            "bed": input_data.bed,
            "bath": input_data.bath,
            "acre_lot": input_data.acre_lot,
            "house_size": input_data.house_size,
            "prev_sold_date": input_data.prev_sold_date,
            # Asumimos que no se envía 'price' en la petición; para compatibilidad con preprocess, lo dejamos NA
        }
        df_raw = pd.DataFrame([data])
    except Exception as e:
        REQUEST_COUNT.labels(endpoint="/predict", http_status="400").inc()
        raise HTTPException(status_code=400, detail=f"Error construyendo el DataFrame de entrada: {e}")

    # ---------------------------------------------------
    # 5.2. Registrar datos de entrada en RAW_DATA (sin procesar)
    # ---------------------------------------------------
    try:
        # Agregar columna 'fetched_at' para registro
        df_to_insert = df_raw.copy()
        df_to_insert["fetched_at"] = datetime.datetime.utcnow()

        # Insertar la fila en la tabla realtor_raw
        with engine_raw.begin() as conn:
            df_to_insert.to_sql("realtor_raw", con=conn, if_exists="append", index=False)
    except Exception as e:
        # No abortamos la inferencia si falla el logging: solo registramos en métricas
        # y seguimos con la predicción. Sin embargo, dejamos rastro en logs
        print(f"[Warning] No se pudo registrar en RAW_DATA: {e}")

    # ---------------------------------------------------
    # 5.3. Preprocesar (igual que en entrenamiento)
    # ---------------------------------------------------
    try:
        df_prepped = preprocess_single(df_raw)
    except Exception as e:
        REQUEST_COUNT.labels(endpoint="/predict", http_status="500").inc()
        raise HTTPException(status_code=500, detail=f"Error en preprocesamiento: {e}")

    # ---------------------------------------------------
    # 5.4. Realizar la predicción con el modelo cargado
    # ---------------------------------------------------
    try:
        # Asegurarnos de pasar solo las columnas que el modelo espera
        # Asumimos que el modelo fue entrenado con exactamente las columnas resultantes de preprocess_single
        pred = model.predict(df_prepped)
        # model.predict devuelve un array, tomamos el primer valor
        predicted_price = float(pred[0])
    except Exception as e:
        REQUEST_COUNT.labels(endpoint="/predict", http_status="500").inc()
        raise HTTPException(status_code=500, detail=f"Error durante la predicción: {e}")

    # ---------------------------------------------------
    # 5.5. Registrar métricas de Prometheus
    # ---------------------------------------------------
    latency = (datetime.datetime.utcnow() - start_time).total_seconds()
    REQUEST_COUNT.labels(endpoint="/predict", http_status="200").inc()
    REQUEST_LATENCY.labels(endpoint="/predict").observe(latency)

    # ---------------------------------------------------
    # 5.6. Responder con el valor predicho
    # ---------------------------------------------------
    return {"predicted_price": predicted_price}

# -------------------------------------------------------
# 6. Endpoint /metrics (Prometheus)
# -------------------------------------------------------

@app.get("/metrics")
def metrics():
    """
    Devuelve todas las métricas de Prometheus en formato text/plain; version=0.0.4
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

# -------------------------------------------------------
# 7. Endpoint de Health Check
# -------------------------------------------------------

@app.get("/health")
def health():
    """
    Verifica que la API esté viva. Retorna 200 OK si el modelo y la base de datos RAW funcionan.
    """
    # Comprobar modelo
    try:
        _ = model.metadata.get("run_id", None)
    except Exception:
        raise HTTPException(status_code=500, detail="Modelo no disponible")

    # Comprobar DB RAW
    try:
        with engine_raw.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=500, detail="DB RAW_DATA no accesible")

    return {"status": "ok"}
