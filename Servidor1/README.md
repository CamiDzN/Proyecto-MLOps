# Servicios en Servidor1

Este README describe en detalle cómo están organizados y desplegados los servicios en **Servidor1** dentro del proyecto `PROYECTO-MLOPS`.

## 🧠 Descripción General del Servidor 1

El **Servidor 1** es el componente encargado de la **ingesta, preprocesamiento y preparación de datos** para el modelo de predicción de precios de propiedades. Su función principal es automatizar el flujo de trabajo de datos utilizando **Apache Airflow**.

### ⚙️ Componentes Clave

- **Apache Airflow**: Orquesta el DAG (`Directed Acyclic Graph`) definido en <mcfile name="realtor_price_model.py" path="c:\Users\luisc\OneDrive\Documents\GitHub\Proyecto-MLOps\Servidor1\dags\realtor_price_model.py"></mcfile>, que gestiona todo el ciclo de vida del preprocesamiento de datos y el entrenamiento del modelo.
- **MySQL**: Base de datos utilizada para almacenar los datos crudos (`realtor_raw`) y los datos preprocesados (`train_clean`, `validation_clean`, `test_clean`).

### 📊 Flujo de Trabajo del DAG (`realtor_price_model.py`)

El DAG <mcsymbol name="realtor_price_model" filename="realtor_price_model.py" path="c:\Users\luisc\OneDrive\Documents\GitHub\Proyecto-MLOps\Servidor1\dags\realtor_price_model.py" startline="30" type="function"></mcsymbol> automatiza los siguientes pasos:

1.  **Extracción de Datos (`extract_data`)**: Se conecta a una API externa para obtener nuevos registros de propiedades. Los datos se insertan en la tabla `realtor_raw` en MySQL. Este paso también verifica si se ha recolectado toda la información mínima necesaria.
2.  **Decisión de Entrenamiento (`decide_train`)**: Un operador de ramificación que decide si se debe proceder con el entrenamiento del modelo. Las condiciones para entrenar incluyen:
    -   Si no hay nuevos registros, el DAG finaliza sin entrenar.
    -   Si se cumplen ciertas validaciones sobre las características de los datos.
    -   Si el número de nuevos registros supera un umbral (ej. 10000), se procede al entrenamiento.
    -   Registra métricas y etiquetas en MLflow sobre la decisión tomada.
3.  **Reinicio de Datos (`reset_data`)**: Si se ha recolectado toda la información mínima necesaria, este paso reinicia la generación de datos en la API externa y trunca las tablas relevantes en las bases de datos `RawData` y `CleanData` para preparar un nuevo ciclo de entrenamiento.
4.  **División de Datos (`split_data`)**: Divide los datos crudos en conjuntos de entrenamiento, validación y prueba, almacenándolos en tablas separadas en MySQL.
5.  **Limpieza de Datos (`clean_data`)**: Realiza el preprocesamiento de los datos, incluyendo la eliminación de valores atípicos, el manejo de valores nulos y la transformación de características. Los datos limpios se almacenan en tablas dedicadas (`train_clean`, `validation_clean`, `test_clean`).
6.  **Entrenamiento del Modelo (`train_model`)**: Entrena un modelo de regresión lineal (o Ridge Regression con GridSearchCV para optimización de hiperparámetros) utilizando los datos limpios. Registra el modelo, las métricas (RMSE) y los parámetros en **MLflow**.
7.  **Evaluación del Modelo (`evaluate_model`)**: Evalúa el modelo entrenado utilizando el conjunto de prueba y registra las métricas finales en MLflow.
8.  **Registro del Modelo (`register_model`)**: Registra el modelo en el **MLflow Model Registry**, gestionando las versiones y las etapas del ciclo de vida del modelo (Staging, Production, Archived).

### 🚀 Despliegue y Ejecución

El despliegue de los servicios en Servidor 1 se realiza a través de **Docker Compose** para Airflow y **Kubernetes** para la base de datos MySQL. Los manifiestos de Kubernetes para MySQL se encuentran en la carpeta `kubernetes/`.

Para ejecutar el DAG, asegúrate de que Airflow esté configurado y que las conexiones a las bases de datos MySQL (`AIRFLOW_CONN_MYSQL_DEFAULT` y `AIRFLOW_CONN_MYSQL_CLEAN`) estén definidas correctamente en el entorno de Airflow.
