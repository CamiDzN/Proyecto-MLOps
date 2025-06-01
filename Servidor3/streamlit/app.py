import streamlit as st
import requests
import mlflow
from mlflow.tracking import MlflowClient
import pandas as pd
import os

# ───── Configuración por entorno ─────
API_URL = os.getenv("API_URL", "http://fastapi:8000/predict")
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_URI)
client = MlflowClient()

st.title("🏠 Realtor Price Prediction")

# ─── Formulario de entrada cruda ───
st.header("🔍 Ingreso de Datos Originales")

inputs = {}
inputs["brokered_by"]     = st.number_input("Brokered by", value=74802.0)
inputs["status"]          = st.selectbox("Status", ["for_sale", "to_build"])
inputs["price"]           = st.number_input("Precio real (para referencia)", value=394900.0)
inputs["bed"]             = st.number_input("Habitaciones", value=3.0)
inputs["bath"]            = st.number_input("Baños", value=2.0)
inputs["acre_lot"]        = st.number_input("Acreaje del lote", value=1.17)
inputs["street"]          = st.number_input("Calle (ID)", value=1589662.0)
inputs["city"]            = st.text_input("Ciudad", value="Crossville")
inputs["state"]           = st.text_input("Estado", value="Tennessee")
inputs["zip_code"]        = st.number_input("Código Postal", value=38571.0)
inputs["house_size"]      = st.number_input("Tamaño casa (pies²)", value=2056.0)
inputs["prev_sold_date"]  = st.date_input("Fecha de última venta", value=pd.to_datetime("2021-12-01"))

if st.button("Predecir"):
    inputs["prev_sold_date"] = inputs["prev_sold_date"].isoformat()
    res = requests.post(API_URL, json=inputs)

    if res.status_code == 200:
        out = res.json()
        st.success(f"Predicción estimada: ${out['prediction']:.2f}")
        st.info(f"Modelo en producción: versión {out['model_version']}")
    else:
        st.error(f"Error {res.status_code}: {res.text}")

# ─── Historial de decisiones y modelos ───
st.header("📊 Historial de Decisiones y Modelos")

runs = client.search_runs(
    experiment_ids=[client.get_experiment_by_name("Realtor_Price_Experiment").experiment_id],
    order_by=["start_time DESC"],
    max_results=500
)

decisions, models = [], []
for r in runs:
    tags = r.data.tags
    if tags.get("decision"):
        decisions.append({
            "Dag_Run_ID": tags.get("dag_run_id"),
            "Decision": tags.get("decision"),
            "Decision Reason": tags.get("reason")
        })
    if tags.get("current_rmse"):
        models.append({
            "Dag_Run_ID": tags.get("dag_run_id"),
            "Model name": "RealtorPriceModel",
            "Model Version": next((v.version for v in client.get_latest_versions("RealtorPriceModel") if v.run_id == r.info.run_id), "N/A"),
            "Current Rsme": tags.get("current_rmse"),
            "Promoted": tags.get("promoted"),
            "Previous Rsme": tags.get("previous_best_rmse")
        })

df_dec = pd.DataFrame(decisions)
df_mod = pd.DataFrame(models)
if not df_dec.empty and not df_mod.empty:
    df = pd.merge(df_dec, df_mod, on="Dag_Run_ID", how="left")
    df = df[["Dag_Run_ID", "Decision", "Decision Reason", "Model name", "Model Version", "Current Rsme", "Promoted", "Previous Rsme"]]
    st.dataframe(df)
else:
    st.warning("No hay datos suficientes en MLflow para mostrar el historial.")