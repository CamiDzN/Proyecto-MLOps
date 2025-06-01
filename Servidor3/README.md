# Servicios en Servidor3

Este README describe en detalle cómo están organizados y desplegados los servicios en **Servidor3** dentro del proyecto `PROYECTO-MLOPS`.

## 🧠 Descripción General del Servidor 3

El **Servidor 3** es una pieza clave en la arquitectura MLOps, encargado de la fase de **despliegue y monitoreo** del modelo de Machine Learning. Este servidor aloja los siguientes componentes:

- **FastAPI**: Una API que expone el modelo de inferencia para su consumo.
- **Streamlit**: Una interfaz de usuario interactiva para visualizar los resultados del modelo y interactuar con él.
- **Prometheus**: Un sistema de monitoreo para recolectar métricas de la API y otros servicios.
- **Grafana**: Una plataforma de visualización que permite crear dashboards a partir de las métricas recolectadas por Prometheus.

Todos estos servicios están orquestados mediante **Kubernetes (MicroK8s)**, lo que garantiza escalabilidad, alta disponibilidad y facilidad de gestión.

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

### 🏗️ Construcción de Imágenes Docker

Navega a los directorios de cada servicio (FastAPI, Streamlit, Prometheus, Grafana) y construye sus respectivas imágenes Docker. Asegúrate de que las imágenes tengan los tags correctos para que Kubernetes pueda encontrarlas.

**FastAPI:**
```bash
cd fastapi
docker build -t camidzn/fastapi-inference:latest .
cd ..
```

**Streamlit:**
```bash
cd streamlit
docker build -t camidzn/streamlit-app:latest .
cd ..
```

**Prometheus:**
```bash
cd prometheus
docker build -t camidzn/prometheus:initial .
cd ..
```

**Grafana:**
```bash
cd grafana
docker build -t camidzn/grafana-dashboard:latest .
cd ..
```

### 🚀 Despliegue en Kubernetes

Una vez que las imágenes Docker estén construidas y disponibles (ya sea localmente o en un registro de Docker), puedes desplegar los servicios en tu clúster de Kubernetes. Asegúrate de que tu `kubeconfig` esté configurado correctamente para apuntar a tu clúster de MicroK8s.

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
