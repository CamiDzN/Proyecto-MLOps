
# 🧠 Descripción General del Proyecto

Este proyecto implementa una solución completa de MLOps distribuida en tres servidores, diseñada para gestionar todo el ciclo de vida de un modelo de machine learning que predice precios de propiedades inmobiliarias.

La arquitectura del proyecto está basada en contenedores Docker orquestados con Kubernetes (MicroK8s) y está organizada en tres entornos funcionales independientes, desplegados en máquinas virtuales diferentes:

- **Servidor 1**: Encargado del preprocesamiento automático de datos con Apache Airflow.
- **Servidor 2**: Responsable del registro de experimentos y gestión de artefactos con MLflow y MinIO.
- **Servidor 3**: Despliega el modelo en producción mediante una API con FastAPI, integra monitoreo con Prometheus & Grafana, pruebas de carga con Locust y una interfaz de usuario con Streamlit.

Este enfoque modular permite escalar y mantener cada componente de forma independiente, emulando un entorno real de producción distribuido.

> 💡 El objetivo principal es proporcionar predicciones precisas de precios inmobiliarios mediante un sistema MLOps completo, permitiendo a los usuarios obtener estimaciones basadas en características de las propiedades.

---

## 🗂️ Distribución del Proyecto por Servidores

Este proyecto fue desarrollado colaborativamente y distribuido en tres máquinas virtuales, cada una encargada de un componente clave del flujo de trabajo MLOps. Cada servidor tiene su propio `README.md` con detalles técnicos y operativos específicos:

| Servidor | Rol Principal                                   | Enlace al Detalle |
|----------|--------------------------------------------------|-------------------|
| 🟦 Servidor 1 | Preprocesamiento de datos con Airflow           | [Ver README Servidor 1](./Servidor1/README.md) |
| 🟩 Servidor 2 | Seguimiento de experimentos con MLflow y MinIO  | [Ver README Servidor 2](./Servidor2/README.md) |
| 🟥 Servidor 3 | Despliegue, monitoreo y pruebas de inferencia   | [Ver README Servidor 3](./Servidor3/README.md) |

Cada una de estas secciones incluye:
- Los contenedores desplegados.
- Los DAGs y notebooks asociados.
- Instrucciones de uso y pruebas.

> 📌 **Nota:** Todos los servidores están conectados en red local y comparten el acceso a la base de datos y el almacenamiento distribuido configurado para simular un entorno de producción real.

---

## 🧱 Arquitectura General del Proyecto

El proyecto está distribuido en **tres servidores (máquinas virtuales)** que trabajan de manera coordinada para implementar un pipeline completo de MLOps. Cada servidor aloja componentes específicos de la arquitectura, asegurando modularidad, escalabilidad y claridad en la implementación.

A continuación se presenta el diagrama de la arquitectura general:

![Arquitectura](public/1. General.png)

### 🔹 Servidor 1 – Preprocesamiento y Almacenamiento de Datos
- **Airflow**: Orquestación de pipelines de preprocesamiento y entrenamiento.
- **Base de Datos MySQL**: Almacena datos en dos capas:
  - `RawData`: Datos crudos separados en train, validation y test.
  - `CleanData`: Datos preprocesados listos para entrenamiento.
- **DAGs**:
  - `realtor_price_model.py`: Preprocesamiento, entrenamiento y registro del modelo de precios inmobiliarios.

### 🔸 Servidor 2 – Seguimiento de Experimentos
- **MLflow Tracking Server**: Registro de métricas, parámetros y artefactos.
- **MinIO**: Almacenamiento compatible con S3 para guardar artefactos de modelos.
- **MySQL Metadata**: Almacena la metadata generada por MLflow.
- Imagen personalizada de MLflow desplegada con dependencias para conectividad segura.

### 🔺 Servidor 3 – Despliegue, Observabilidad y Experiencia de Usuario
- **FastAPI**: API de inferencia conectada al modelo en producción desde MLflow.
- **Streamlit**: Interfaz gráfica para realizar predicciones desde la web.
- **Prometheus + Grafana**: Monitoreo del comportamiento de la API:
  - Latencia, uso de memoria, conteo de inferencias.

> 🧩 Cada componente se desplegó como contenedor independiente y se conectó a través de redes virtuales internas. Las IPs asignadas por el clúster a cada servidor aseguran el enrutamiento correcto entre servicios.

---
## 🛠️ Tecnologías y Componentes Utilizados

El proyecto se compone de varios microservicios, cada uno desplegado en contenedores independientes, comunicados entre sí dentro de un entorno orquestado con Kubernetes:

- **MLflow**: Gestión de experimentos y modelos. Conectado a MinIO (artefactos) y MySQL (metadatos).
- **Airflow**: Orquestación de pipelines de preprocesamiento y entrenamiento.
- **MinIO**: Almacenamiento local de artefactos, compatible con S3.
- **MySQL**: Bases de datos para RawData, CleanData y metadata de MLflow y Airflow.

- **FastAPI**: API de inferencia del modelo en producción.
- **Streamlit**: Interfaz gráfica para predicciones del modelo.
- **Prometheus + Grafana**: Observabilidad y monitoreo de métricas de inferencia.


## 🚀 ¿Cómo ejecutar el proyecto completo?
✅ Asegúrate de que los 3 servidores estén activos, conectados en la misma red y con Kubernetes (MicroK8s) habilitado.

🔌 Paso a paso por servidor
🖥️ Servidor 1 — Preprocesamiento y orquestación

```bash
kubectl apply -f Servidor1/kubernetes/
```
Accede a Airflow y ejecuta el DAG realtor_price_model.py.

🗃️ Servidor 2 — Almacenamiento y MLflow

```bash
docker build -t custom-mlflow:latest .
docker tag custom-mlflow:latest localhost:32000/custom-mlflow:latest
docker push localhost:32000/custom-mlflow:latest
kubectl apply -f Servidor2/kubernetes/
kubectl apply -f Servidor2/kubernetes/create-minio-bucket.yaml
```

📡 Servidor 3 — Inferencia, monitoreo y UI

```bash
kubectl apply -f Servidor3/kubernetes/
```

Accede a la API o interfaz de Streamlit para hacer predicciones.
Verifica métricas en Prometheus y visualízalas en Grafana.
