# 🧠 Descripción General del Proyecto

Este proyecto implementa una solución completa de MLOps distribuida en tres servidores, diseñada para gestionar todo el ciclo de vida de un modelo de machine learning.

La arquitectura del proyecto está basada en contenedores Docker orquestados con Kubernetes (MicroK8s) y está organizada en tres entornos funcionales independientes, desplegados en máquinas virtuales diferentes:

 
#### 📂 Estructura Detallada de Carpeta - **[Servidor 1](Servidor1/README.md)**
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



