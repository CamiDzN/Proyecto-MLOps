# 🧠 Descripción General del Proyecto

Este proyecto implementa una solución completa de MLOps distribuida en tres servidores, diseñada para gestionar todo el ciclo de vida de un modelo de machine learning.

La arquitectura del proyecto está basada en contenedores Docker orquestados con Kubernetes (MicroK8s) y está organizada en tres entornos funcionales independientes, desplegados en máquinas virtuales diferentes:

- **Servidor 1**: Encargado del preprocesamiento automático de datos con Apache Airflow.
- **Servidor 2**: Responsable del registro de experimentos y gestión de artefactos con MLflow y MinIO.
- **Servidor 3**: Despliega el modelo en producción mediante una API con FastAPI, integra monitoreo con Prometheus & Grafana y una interfaz de usuario con Streamlit.

Este enfoque modular permite escalar y mantener cada componente de forma independiente, emulando un entorno real de producción distribuido.