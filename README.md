# 🧠 Descripción General del Proyecto

Este proyecto implementa una solución completa de MLOps distribuida en tres servidores, diseñada para gestionar todo el ciclo de vida de un modelo de machine learning.

La arquitectura del proyecto está basada en contenedores Docker orquestados con Kubernetes (MicroK8s) y está organizada en tres entornos funcionales independientes, desplegados en máquinas virtuales diferentes:

- **Servidor 1**: Contiene la configuración de Apache Airflow para el preprocesamiento automático de datos. El archivo clave es `Servidor1/dags/realtor_price_model.py`, que define el DAG encargado de la extracción, preprocesamiento y división de datos, así como el entrenamiento y registro de modelos de Machine Learning.
- **Servidor 2**: Responsable del registro de experimentos y gestión de artefactos con MLflow y MinIO. La carpeta `Servidor2/k8s/argo-cd/` es fundamental, ya que contiene los manifiestos de ArgoCD para el despliegue automatizado de los servicios en los diferentes servidores (Servidor1, Servidor2 y Servidor3).
- **Servidor 3**: Despliega el modelo en producción mediante una API con FastAPI, integra monitoreo con Prometheus & Grafana y una interfaz de usuario con Streamlit. La carpeta `Servidor3/k8s/` contiene todos los manifiestos de Kubernetes para orquestar estos servicios, con `kustomization.yaml` gestionando las etiquetas de las imágenes Docker y los recursos.

Este enfoque modular permite escalar y mantener cada componente de forma independiente, emulando un entorno real de producción distribuido.

## 📂 Estructura Detallada de Carpetas

### Servidor1
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

### Servidor2
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

### Servidor3
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