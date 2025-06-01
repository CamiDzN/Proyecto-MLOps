# Servicios en Servidor3

Este README describe en detalle cómo están organizados y desplegados los servicios en **Servidor3** dentro del proyecto `PROYECTO-MLOPS`.

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

## 🚀 Despliegue y Ejecución

Para desplegar y ejecutar los servicios en el **Servidor 3**, sigue los siguientes pasos:

### 📋 Requisitos Previos

Asegúrate de tener instalados los siguientes componentes en tu sistema:

- **Git**: Para clonar el repositorio.
- **Docker**: Para construir las imágenes de los contenedores.
- **kubectl**: La herramienta de línea de comandos de Kubernetes.
- **MicroK8s**: Un clúster de Kubernetes ligero (o cualquier otro clúster de Kubernetes configurado).

### ⬇️ Clonación del Repositorio

Clona el repositorio principal del proyecto:

```bash
git clone https://github.com/CamiDzN/Proyecto-MLOps.git
cd Proyecto-MLOps/Servidor3
```

### 🚀 Despliegue en Kubernetes

Las imágenes Docker para los servicios (FastAPI, Streamlit, Prometheus, Grafana) se obtienen directamente desde Docker Hub. Asegúrate de que tu `kubeconfig` esté configurado correctamente para apuntar a tu clúster de MicroK8s.

Navega al directorio `k8s` dentro de `Servidor3` y aplica los manifiestos de Kubernetes:

```bash
cd k8s
kubectl apply -f .
```

Esto desplegará los Deployments, Services, ConfigMaps y otros recursos necesarios para FastAPI, Streamlit, Prometheus y Grafana.

### 🌐 Acceso a los Servicios

Una vez que los pods estén en ejecución, puedes acceder a los servicios:

- **FastAPI**: El servicio de FastAPI estará disponible internamente en el clúster. Si necesitas acceder desde fuera, puedes configurar un `NodePort` o `Ingress`.
- **Streamlit**: Accede a la interfaz de Streamlit a través del `NodePort` o `Ingress` configurado en `streamlit-service.yaml`.
- **Prometheus**: Accede a la interfaz de Prometheus a través del `NodePort` configurado en `prometheus-service.yaml`.
- **Grafana**: Accede a la interfaz de Grafana a través del `NodePort` configurado en `grafana-service.yaml`. Las credenciales por defecto suelen ser `admin/admin`.

Para obtener los `NodePort`s, puedes ejecutar:

```bash
kubectl get services -n default
```

Busca los puertos asignados a `streamlit-service`, `prometheus-service` y `grafana-service`.
