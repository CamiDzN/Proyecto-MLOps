## 🧠 Proyecto MLOps - Servidor 2

### 📌 Descripción General

Este entorno representa la implementación de un sistema MLOps completo desde el **Servidor 2**, usando:

* **ArgoCD** como herramienta de GitOps para el despliegue automatizado.
* **MLflow** para el registro y seguimiento de modelos.
* **MinIO** como almacenamiento de artefactos.
* **PostgreSQL** como base de datos.

Se incluyen también configuraciones de GitHub Actions para integración continua de componentes.

---

### 🗂️ Estructura del Proyecto (Servidor 2)

```
Servidor2/
├── k8s/
│   ├── argo-cd/
│   │   ├── app.yaml             
│   │   ├── app-servidor1.yaml     
│   │   ├── app-servidor3.yaml       
│   │   ├── create-minio-bucket.yaml 
│   │   └── install.yaml             
│   ├── kustomization.yaml          
│   ├── minio-deployment.yaml        
│   ├── minio-service.yaml           
│   ├── mlflow-deployment.yaml       
│   ├── mlflow-service.yaml          
│   ├── namespace.yaml
│   ├── create-minio-bucket.yaml                
│   ├── postgres-deployment.yaml     
│   └── postgres-service.yaml        
├── mlflow/                         
├── kubeconfig-servidor1.yaml        
├── kubeconfig-servidor3.yaml       
└── README.md                        

.github/workflows/
├── ci-cd-airflow.yaml   
├── ci-cd-servidor2.yaml  
└── ci-cd-servidor3.yaml  
```

> **Nota sobre `kubeconfig-servidor*.yaml`:**
>
> * Estos archivos contienen las credenciales y contexto de cada clúster remoto (Servidor 1 y Servidor 3).
> * Se utilizan en ArgoCD (`argocd cluster add`) para que ArgoCD, instalado en Servidor 2, pueda desplegar directamente en esos clústeres.

---

### ⚙️ Flujo ArgoCD - Servidor 2

1. **Creación de namespace (opcional)**
   Si no se usa el espacio `default`, ejecutar:

   ```bash
   microk8s kubectl create namespace mlops
   ```

   Esto se hace una sola vez en cada clúster (Servidor 2, Servidor 1 y Servidor 3), para alinear el Namespace usado en los manifiestos.

2. **Registrar clústeres remotos en ArgoCD**
   En Servidor 2, con los kubeconfig copiados:

   ```bash
   KUBECONFIG=./kubeconfig-servidor1.yaml argocd cluster add microk8s   
   KUBECONFIG=./kubeconfig-servidor3.yaml argocd cluster add microk8s   
   ```

   * Esto crea un ServiceAccount `argocd-manager` en cada clúster remoto y configura el acceso.

3. **Configurar applications en ArgoCD**

   * `k8s/argo-cd/app.yaml`:     despliega **Servidor 2** (apunta a `Servidor2/k8s`, rama  `main`).
   * `k8s/argo-cd/app-servidor1.yaml`: despliega manifiestos de **Servidor 1** (path `Servidor1/kubernetes`).
   * `k8s/argo-cd/app-servidor3.yaml`: despliega manifiestos de **Servidor 3** (path `Servidor3/k8s`).

   Por ejemplo, `app.yaml` para Servidor 2:

   ```yaml
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: proyecto-mlops-daniel
     namespace: argocd
   spec:
     project: default
     source:
       repoURL: https://github.com/CamiDzN/Proyecto-MLOps
       targetRevision: main              
       path: Servidor2/k8s                   # Carpeta donde están los manifiestos de Servidor 2
     destination:
       server: https://kubernetes.default.svc  # Clúster local de MicroK8s en Servidor 2
       namespace: mlops
     syncPolicy:
       automated:
         selfHeal: true
         prune: true
   ```

4. **Aplicar y sincronizar**

   ```bash
   microk8s kubectl apply -f k8s/argo-cd/app.yaml -n argocd
   argocd app sync proyecto-mlops-daniel --prune --force
   ```

   * Verificar que el estado pase a `Synced` y `Healthy`.

---

### 🧪 Validación y Monitoreo

* **Pods y servicios** en Servidor 2:

  ```bash
  microk8s kubectl get pods -n mlops
  microk8s kubectl get svc -n mlops
  ```
  
![image](https://github.com/user-attachments/assets/60a6ca68-881b-454a-95e7-3450b934334d)

* **ArgoCD UI**: 

  * Acceder a `https://<IP_Servidor2>:<puerto>` o mediante `port-forward`:

    ```bash
    kubectl port-forward svc/argocd-server -n argocd 8080:443
    ```
  * Verificar que `proyecto-mlops-daniel`, `servidor1-mlops` y `servidor3-mlops` estén `Synced` y `Healthy`.

* Servidor 1
 ![image](https://github.com/user-attachments/assets/1276e1e2-3335-45e4-b08a-11e5310af192)
* Servidor 2
 ![image](https://github.com/user-attachments/assets/0fc2fe1f-5ac0-493a-8324-e70be9043179)
* Servidor 3
 ![image](https://github.com/user-attachments/assets/cbbad1de-8cda-4a2f-b8c1-220ece249286)

## 4. **Despliegue Manual**

### 1. Construir y etiquetar la imagen de MLflow
```bash
cd Servidor2/mlflow
docker build -t camidzn/mlflow-custom:initial .
docker tag camidzn/mlflow-custom:initial localhost:32000/custom-mlflow:initial
   ```
### 2. Enviar la imagen al registry local
```bash
docker push localhost:32000/custom-mlflow:initial
   ```
### 3. Crear namespace (si aún no existe)
```bash
kubectl create namespace mlops
   ```
### 4. Aplicar los manifiestos de Servidor2
```bash
cd ../../Servidor2/k8s
kubectl apply -f .
kubectl apply -f create-minio-bucket.yaml
   ```

