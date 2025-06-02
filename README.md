# 🧠 Descripción General del Proyecto

Este proyecto implementa una solución completa de MLOps distribuida en tres servidores, diseñada para gestionar todo el ciclo de vida de un modelo de machine learning.

La arquitectura del proyecto está basada en contenedores Docker orquestados con Kubernetes (MicroK8s) y está organizada en tres entornos funcionales independientes, desplegados en máquinas virtuales diferentes:

 
#### 📂 Estructura Detallada de Carpeta - **[Servidor 1](Servidor1/README.md)**:
```
├── .env
├── README.md
├── airflow\
│   ├── Dockerfile
│   └── requirements.txt
├── dags\
│   └── realtor_price_model.py
├── docker-compose.yaml
├── kubeconfig-servidor1.yaml
└── kubernetes\
    ├── mysql-deployment.yaml
    ├── mysql-init-configmap.yaml
    ├── mysql-pvc.yaml
    └── mysql-service.yaml
```

Dedicado a la ingesta, preprocesamiento y preparación de datos. Incluye la configuración de Apache Airflow en la carpeta `airflow/` con su `Dockerfile` y `requirements.txt`, y el DAG principal `realtor_price_model.py` en `dags/` para la orquestación del flujo de datos. La base de datos MySQL se gestiona con manifiestos de Kubernetes en `kubernetes/` (despliegue, configmap de inicialización, PVC y servicio). También contiene `docker-compose.yaml` para el entorno de desarrollo y `kubeconfig-servidor1.yaml` para la conexión al clúster.
 

#### 📂 Estructura Detallada de Carpeta - **[Servidor 2](Servidor2/README.md)**:

```
├── README.md
├── k8s\
│   ├── argo-cd\
│   │   ├── app-servidor1.yaml
│   │   ├── app-servidor3.yaml
│   │   ├── app.yaml
│   │   └── install.yaml
│   ├── create-minio-bucket.yaml
│   ├── kustomization.yaml
│   ├── minio-deployment.yaml
│   ├── minio-service.yaml
│   ├── mlflow-deployment.yaml
│   ├── mlflow-service.yaml
│   ├── namespace.yaml
│   ├── postgres-deployment.yaml
│   └── postgres-service.yaml
├── kubeconfig-servidor1.yaml
├── kubeconfig-servidor3.yaml
└── mlflow\
    └── Dockerfile
```


Centraliza el registro de experimentos y la gestión de artefactos. La carpeta `k8s/` contiene todos los manifiestos de Kubernetes para desplegar MLflow, MinIO y PostgreSQL, incluyendo `minio-deployment.yaml`, `mlflow-deployment.yaml`, `postgres-deployment.yaml` y sus respectivos servicios. Dentro de `k8s/argo-cd/` se encuentran las definiciones de aplicaciones de ArgoCD (`app.yaml`, `app-servidor1.yaml`, `app-servidor3.yaml`) para la automatización de despliegues en los tres servidores. La carpeta `mlflow/` contiene el `Dockerfile` para la imagen de MLflow. También incluye `kubeconfig-servidor1.yaml` y `kubeconfig-servidor3.yaml` para la conexión a los clústeres remotos.

#### 📂 Estructura Detallada de Carpeta - **[Servidor 3](Servidor3/README.md)**:
```
├── README.md
├── fastapi\
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── grafana\
│   ├── Dockerfile
│   └── provisioning\
│       ├── dashboards.yml
│       └── datasources.yml
├── k8s\
│   ├── api-deployment.yaml
│   ├── api-service.yaml
│   ├── grafana-configmap.yaml
│   ├── grafana-dashboards-configmap.yaml
│   ├── grafana-deployment.yaml
│   ├── grafana-ini-overrides.yaml
│   ├── grafana-service.yaml
│   ├── kustomization.yaml
│   ├── prometheus-configmap.yaml
│   ├── prometheus-deployment.yaml
│   ├── prometheus-service.yaml
│   ├── streamlit-deployment.yaml
│   └── streamlit-service.yaml
├── kubeconfig-servidor3.yaml
├── prometheus\
│   ├── Dockerfile
│   └── prometheus.yml
└── streamlit\
    ├── Dockerfile
    ├── app.py
    └── requirements.txt
```

Encargado del despliegue y monitoreo del modelo en producción. Aloja una API con FastAPI (`fastapi/`), una interfaz de usuario con Streamlit (`streamlit/`), monitoreo con Prometheus (`prometheus/`) y visualización con Grafana (`grafana/`). Cada una de estas carpetas contiene su `Dockerfile` y archivos de configuración (`main.py` para FastAPI, `app.py` para Streamlit, `prometheus.yml` para Prometheus, y `provisioning/` para Grafana). La carpeta `k8s/` es crucial, ya que contiene todos los manifiestos de Kubernetes (`api-deployment.yaml`, `grafana-deployment.yaml`, `prometheus-deployment.yaml`, `streamlit-deployment.yaml` y sus servicios y configmaps asociados), con `kustomization.yaml` para la gestión de recursos y etiquetas de imágenes Docker. También incluye `kubeconfig-servidor3.yaml` para la conexión al clúster.

Este enfoque modular permite escalar y mantener cada componente de forma independiente, emulando un entorno real de producción distribuido.

## 🧠 Descripción General del Servidor 3

El **Servidor 3** es una pieza clave en la arquitectura MLOps, encargado de la fase de **despliegue y monitoreo** del modelo de Machine Learning. Este servidor aloja los siguientes componentes:

- **FastAPI**: Una API RESTful que expone el modelo de inferencia de precios de propiedades. Se encarga de:
  - Recibir datos crudos de entrada.
  - Preprocesar los datos para alinearlos con el formato esperado por el modelo.
  - Cargar el modelo de Machine Learning desde MLflow (en etapa de Producción).
  - Realizar predicciones.
  - Almacenar los datos de entrada en una base de datos (PostgreSQL).
  - Exponer métricas de Prometheus para monitoreo (contador de peticiones y latencia).
- **Streamlit**: Una aplicación web interactiva que sirve como interfaz de usuario para el modelo de predicción. Permite a los usuarios:
  - Ingresar datos de propiedades a través de un formulario.
  - Enviar estos datos a la API de FastAPI para obtener predicciones.
  - Mostrar la predicción estimada y la versión del modelo utilizada.
  - Visualizar el historial de decisiones y modelos registrados en MLflow, incluyendo métricas como RMSE y el estado de promoción de los modelos.
- **Prometheus**: Un sistema de monitoreo para recolectar métricas de la API y otros servicios.
- **Grafana**: Una plataforma de visualización que permite crear dashboards a partir de las métricas recolectadas por Prometheus.

Todos estos servicios están orquestados mediante **Kubernetes (MicroK8s)**, lo que garantiza escalabilidad, alta disponibilidad y facilidad de gestión.

### 🗂️ Estructura de la Carpeta `k8s`

La carpeta `k8s` contiene todos los manifiestos de Kubernetes necesarios para desplegar los servicios de FastAPI, Streamlit, Prometheus y Grafana en el clúster. Estos archivos definen los `Deployments`, `Services`, `ConfigMaps` y otros recursos que orquestan la aplicación.

El archivo clave en esta carpeta es `kustomization.yaml`:

- **`kustomization.yaml`**: Este archivo es utilizado por Kustomize (una herramienta nativa de Kubernetes) para personalizar y combinar los manifiestos de Kubernetes. En este proyecto, `kustomization.yaml` se encarga de:
  - Listar todos los recursos (`.yaml` files) que deben ser aplicados al clúster (Deployments, Services, ConfigMaps, etc.).
  - Gestionar las etiquetas de las imágenes Docker, permitiendo actualizar las versiones de las imágenes de los servicios (FastAPI, Grafana, Prometheus, Streamlit) de manera centralizada.


