## 🧠 Proyecto MLOps - Servidor 2

### 📌 Descripción General

Este entorno representa la implementación de un sistema MLOps completo desde el Servidor 2, usando ArgoCD como herramienta de GitOps para el despliegue automatizado, MLflow para el registro y seguimiento de modelos, MinIO como almacenamiento de artefactos, y PostgreSQL como base de datos.

---

### 🗂️ Estructura del Servidor 2

```bash
Servidor2/
├── k8s/
│   ├── argo-cd/
│   │   ├── app.yaml
│   │   └── create-minio-bucket.yaml
│   ├── kustomization.yaml
│   ├── minio-deployment.yaml
│   ├── minio-service.yaml
│   ├── mlflow-deployment.yaml
│   ├── mlflow-service.yaml
│   ├── namespace.yaml
│   ├── postgres-deployment.yaml
│   └── postgres-service.yaml
├── mlflow/                # (Ignorado en despliegue, imagen desde Docker Hub)
├── kubeconfig-servidor1.yaml
├── kubeconfig-servidor3.yaml
└── README.md
```

También se cuenta con configuración de GitHub Actions en:

```bash
.github/workflows/
├── ci-cd-airflow.yaml
├── ci-cd-servidor2.yaml
└── ci-cd-servidor3.yaml
```

---

### ⚙️ Flujo ArgoCD - Servidor 2

1. Se configura `app.yaml` apuntando a la rama `DanielR` y al path `Servidor2/k8s`.
2. Se crea el namespace (si no se usa `default`) en el clúster:

   ```bash
   kubectl create namespace mlops
   ```
3. Se aplica la aplicación en ArgoCD:

   ```bash
   microk8s kubectl apply -f k8s/argo-cd/app.yaml -n argocd
   ```
4. Se sincroniza:

   ```bash
   argocd app sync proyecto-mlops-daniel --prune --force
   ```

---

### 🧪 Validación desde ArgoCD

La aplicación debe aparecer en estado `Synced` y `Healthy`. Puedes validar que:

* MLflow, MinIO y PostgreSQL estén corriendo correctamente:

  ```bash
  microk8s kubectl get pods -n mlops
  ```
* Visualmente, desde la interfaz de ArgoCD se muestra el estado de los recursos del Servidor 2.

* Servidor 1
* ![image](https://github.com/user-attachments/assets/1276e1e2-3335-45e4-b08a-11e5310af192)
* Servidor 2
 ![image](https://github.com/user-attachments/assets/0fc2fe1f-5ac0-493a-8324-e70be9043179)
* Servidor 3
* ![image](https://github.com/user-attachments/assets/cbbad1de-8cda-4a2f-b8c1-220ece249286)
