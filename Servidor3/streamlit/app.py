import streamlit as st
import pandas as pd
import numpy as np
import shap
from prometheus_client import start_http_server, Summary

# Arranca el servidor Prometheus para métricas
start_http_server(8501)
REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')

@REQUEST_TIME.time()
def load_data():
    # Simula carga de datos
    data = pd.DataFrame(np.random.rand(100, 5), columns=[f"feature_{i}" for i in range(5)])
    return data

@st.cache_data
def get_shap_values(data):
    # Explicador SHAP sencillo usando media
    explainer = shap.Explainer(lambda x: np.mean(x, axis=1), data)
    shap_values = explainer(data)
    return shap_values

st.title("Demo Streamlit con SHAP")

data = load_data()
st.subheader("Datos de muestra")
st.dataframe(data.head())

# Cálculo y gráfico de SHAP
shap_values = get_shap_values(data)
st.subheader("Gráfico de SHAP para la primera muestra")
shap.plots.waterfall(shap_values[0])
