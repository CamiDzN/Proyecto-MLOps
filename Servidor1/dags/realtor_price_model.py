import os
import datetime
import requests
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import ProgrammingError
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import GridSearchCV
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule

# Parámetros del DAG
default_args = {
    "owner": "airflow",
    "start_date": datetime.datetime(2025, 5, 1),
    "retries": 1,
    "retry_delay": datetime.timedelta(minutes=5),
}

with DAG(
    dag_id="realtor_price_model",
    default_args=default_args,
    schedule_interval="@daily",
    catchup=False,
    tags=["realtor", "mlflow"],
) as dag:


    def extract_data(**context):
        """
        Llama a /data?group_number=7&day=Tuesday.
        - Si viene un dict con 'data', extrae la lista de payload['data'].
        - Inserta sólo rows > 0.
        - Sólo el HTTP 400 con el mensaje de fin marca finished=True.
        """
        RAW_URI = os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT")
        engine = create_engine(RAW_URI)

        url = "http://10.43.101.108:80/data"
        params = {"group_number": 7, "day": "Tuesday"}

        finished = False
        new_records = 0

        try:
            resp = requests.get(url, params=params)
            logging.info(f"extract_data → HTTP {resp.status_code} response.text:\n{resp.text}")
            resp.raise_for_status()

            payload = resp.json()
            logging.info(f"extract_data → payload type: {type(payload)}, keys: {getattr(payload, 'keys', lambda: '')()}")

            # 1) Extraer rows bien sea lista directa o dentro de payload['data']
            if isinstance(payload, dict) and "data" in payload:
                rows = payload["data"] or []
            elif isinstance(payload, list):
                rows = payload
            else:
                rows = []

            logging.info(f"extract_data → rows extraídas (len): {len(rows)}")

            # 2) Insertar sólo si llega algo
            if rows:
                df = pd.DataFrame(rows)
                df["fetched_at"] = datetime.datetime.utcnow()
                df.to_sql("realtor_raw", con=engine, if_exists="append", index=False)
                new_records = len(rows)
                logging.info(f"extract_data → insertadas {new_records} filas en realtor_raw")
            else:
                logging.info("extract_data → no hay filas nuevas (rows vacío), finished sigue False")

        except requests.exceptions.HTTPError as e:
            resp = e.response
            if resp is not None and resp.status_code == 400:
                # Sólo este 400 concreto marca fin
                try:
                    detail = resp.json().get("detail", "")
                except ValueError:
                    detail = resp.text
                logging.info(f"extract_data → HTTP 400 detalle: {detail!r}")
                if "Ya se recolectó toda la información mínima necesaria" in detail:
                    finished = True
                    logging.info("extract_data → fin de datos detectado; marcar finished=True")
            else:
                raise

        # 3) Guardar en XCom
        ti = context["ti"]
        ti.xcom_push(key="new_records", value=new_records)
        ti.xcom_push(key="finished", value=finished)


    extract_task = PythonOperator(
        task_id="extract_data",
        python_callable=extract_data,
        provide_context=True,
    )

    def branch_on_exhaustion(**context):
        finished = context["ti"].xcom_pull(key="finished", task_ids="extract_data")
        return "reset_data" if finished else "decide_to_train"

    branch_exhaust = BranchPythonOperator(
        task_id="branch_on_exhaustion",
        python_callable=branch_on_exhaustion,
        provide_context=True,
    )

    def reset_data(**context):
        """
        Llama al endpoint /restart_data_generation y luego vacía (TRUNCATE)
        sólo las tablas que existan en RawData y CleanData.
        """
        # 1) Llamada al endpoint de reinicio
        url = "http://10.43.101.108:80/restart_data_generation"
        params = {"group_number": 7, "day": "Tuesday"}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        logging.info("reset_data → restart_data_generation OK")

        # 2) Engines y inspectors
        RAW_URI = os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT")
        CLEAN_URI = os.getenv("AIRFLOW_CONN_MYSQL_CLEAN")
        engine_raw   = create_engine(RAW_URI)
        engine_clean = create_engine(CLEAN_URI)
        insp_raw     = inspect(engine_raw)
        insp_clean   = inspect(engine_clean)

        # 3) Listado de tablas a truncar
        tablas_raw   = ["realtor_raw", "train", "validation", "test"]
        tablas_clean = ["train_clean", "validation_clean", "test_clean"]

        # 4) Truncar sólo si la tabla existe
        with engine_raw.begin() as conn:
            for table in tablas_raw:
                if insp_raw.has_table(table):
                    conn.execute(text(f"TRUNCATE TABLE `{table}`"))
                    logging.info(f"reset_data → tabla RawData.{table} truncada")
                else:
                    logging.info(f"reset_data → tabla RawData.{table} NO existe, omitiendo")

        with engine_clean.begin() as conn:
            for table in tablas_clean:
                if insp_clean.has_table(table):
                    conn.execute(text(f"TRUNCATE TABLE `{table}`"))
                    logging.info(f"reset_data → tabla CleanData.{table} truncada")
                else:
                    logging.info(f"reset_data → tabla CleanData.{table} NO existe, omitiendo")

    reset_task = PythonOperator(
        task_id="reset_data",
        python_callable=reset_data,
    )


    def decide_train(**context):
        """
        BranchPythonOperator para decidir si entrenar:
        - new_records == 0          → end_no_train
        - validaciones sobre FEATURES → end_no_train
        - new_records > 10000         → split_data
        - en otros casos           → end_no_train

        Además registra en MLflow:
        - métrica new_records
        - tags: decision, reason, dag_run_id, execution_date
        """
        # 0) Configurar MLflow
        mlflow.set_tracking_uri(os.getenv("AIRFLOW_VAR_MLFLOW_TRACKING_URI"))
        mlflow.set_experiment("Realtor_Price")

        ti = context["ti"]
        dag_run = context["dag_run"]
        new_records = ti.xcom_pull(key="new_records", task_ids="extract_data") or 0

        # Early exit sin datos nuevos
        if new_records == 0:
            with mlflow.start_run(run_name="decision"):
                mlflow.log_metric("new_records", 0)
                mlflow.set_tag("decision", "end_no_train")
                mlflow.set_tag("reason", "0 new records")
                mlflow.set_tag("dag_run_id", dag_run.run_id)
                mlflow.set_tag("execution_date", context["execution_date"].isoformat())
            return "end_no_train"

        # 1) Leer los últimos new_records
        engine = create_engine(os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT"))
        df = pd.read_sql(
            text("""
                SELECT *
                FROM realtor_raw
                ORDER BY fetched_at DESC
                LIMIT :n
            """),
            con=engine,
            params={"n": new_records},
        )

        # 2) Validaciones sólo sobre las columnas que usaremos después
        features = ["status", "bed", "bath", "acre_lot", "house_size", "prev_sold_date", "price"]
        invalid = []

        # 2.1) Columnas faltantes
        missing = set(features) - set(df.columns)
        if missing:
            invalid.append(f"Faltan columnas: {sorted(missing)}")

        if not missing:
            # 2.2) Nulos
            nulls = df[features].isnull().any()
            if nulls.any():
                invalid.append(f"Nulos en: {nulls[nulls].index.tolist()}")

            # 2.3) Rangos y formatos (solo si no hay nulos)
           # if not nulls.any():
           #     if (df["price"] <= 0).any():
           #         invalid.append("price ≤ 0")
           #     bad_bed = df[(df["bed"] < 0) | (df["bed"] > 10) | ((df["bed"] % 1) != 0)]
           #     if not bad_bed.empty:
           #         invalid.append("bed fuera de [0–10] o no entero")
           #     bad_bath = df[(df["bath"] < 0) | (df["bath"] > 10) | ((df["bath"] % 1) != 0)]
           #     if not bad_bath.empty:
           #         invalid.append("bath fuera de [0–10] o no entero")
           #     if ((df["acre_lot"] <= 0) | (df["acre_lot"] > 1000)).any():
           #         invalid.append("acre_lot fuera de (0,1000]")
           #     valid_status = ["for_sale", "to_build"]
           #     if not df["status"].isin(valid_status).all():
           #         invalid.append(f"status no en {valid_status}")
           #     # prev_sold_date debe ser parseable
           #     try:
           #         pd.to_datetime(df["prev_sold_date"])
           #     except Exception:
           #         invalid.append("prev_sold_date no parseable")

        # 3) Registrar en MLflow y decidir branch
        with mlflow.start_run(run_name="decision"):
            mlflow.log_metric("new_records", new_records)
            mlflow.set_tag("dag_run_id", dag_run.run_id)
            mlflow.set_tag("execution_date", context["execution_date"].isoformat())

            if invalid:
                branch, reason = "end_no_train", " & ".join(invalid)
            elif new_records > 10000:
                branch, reason = "split_data", f"{new_records} nuevos > 10000"
            else:
                branch, reason = "end_no_train", f"{new_records} nuevos ≤ 10000"

            mlflow.set_tag("decision", branch)
            mlflow.set_tag("reason", reason)

        logging.info(f"decide_train → voy a rama «{branch}» porque new_records={new_records}, reason={reason}")

        return branch

    decide_task = BranchPythonOperator(
        task_id="decide_to_train",
        python_callable=decide_train,
        provide_context=True,
    )


    # ──────────────────────────────────────────────────────────────────────────────
    # 1) split_data: usa TODO realtor_raw para repartir 60/20/20 y sobreescribe
    #    las tablas train, validation y test en la misma BD de RawData.
    # ──────────────────────────────────────────────────────────────────────────────
    def split_data():
        RAW_URI = os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT")
        engine  = create_engine(RAW_URI)

        # 1.1) Cargo TODO el histórico
        df = pd.read_sql_table("realtor_raw", con=engine)
        n  = len(df)
        logging.info(f"split_data → {n} registros totales en realtor_raw")

        if n == 0:
            logging.info("split_data → No hay datos en realtor_raw, saliendo.")
            return

        # 1.2) Mezclo y parto
        df = df.sample(frac=1, random_state=42)
        i1 = int(0.6 * n)
        i2 = int(0.8 * n)
        train_df = df.iloc[:i1]
        val_df   = df.iloc[i1:i2]
        test_df  = df.iloc[i2:]

        # 1.3) Sobrescribo los splits en RawData
        with engine.begin() as conn:
            train_df.to_sql( "train",      conn, if_exists="replace", index=False)
            val_df.to_sql(   "validation", conn, if_exists="replace", index=False)
            test_df.to_sql(  "test",       conn, if_exists="replace", index=False)

        logging.info(
            f"split_data → splits escritos: "
            f"train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
        )

    split_task = PythonOperator(
        task_id="split_data",
        python_callable=split_data,
    )


    # ──────────────────────────────────────────────────────────────────────────────
    # 2) preprocess_data: lee los splits recién recreados en RawData,
    #    aplica tu función _prep, y sobrescribe los splits en CleanData.
    # ──────────────────────────────────────────────────────────────────────────────
    def preprocess_data():
        RAW_URI   = os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT")
        CLEAN_URI = os.getenv("AIRFLOW_CONN_MYSQL_CLEAN")
        engine_raw   = create_engine(RAW_URI)
        engine_clean = create_engine(CLEAN_URI)

        def _prep(df: pd.DataFrame) -> pd.DataFrame:
            # 1) Rellenar numéricos
            num_cols = ["bed","bath","acre_lot","house_size","price"]
            df[num_cols] = df[num_cols].fillna(method="ffill").fillna(0)

            # 2) days_since_last_sale (tz-naive – tz-naive)
            df["prev_sold_date"] = pd.to_datetime(
                df["prev_sold_date"], errors="coerce"
            )
            # ahora both son tz-naive
            now = datetime.datetime.utcnow()
            df["days_since_last_sale"] = (
                (now - df["prev_sold_date"])
                .dt.days
                .fillna(-1)
                .astype(int)
            )

            # 3) One-hot de status
            df = pd.get_dummies(df, columns=["status"], drop_first=True)

            # 4) Eliminar columnas de alta cardinalidad
            drop_cols = [
                "brokered_by",
                "street",
                "zip_code",
                "city",
                "state",
                "prev_sold_date",
                "fetched_at",
            ]
            df = df.drop(columns=[c for c in drop_cols if c in df.columns])

            # 5) Poner price al final
            if "price" in df.columns:
                cols = [c for c in df.columns if c != "price"] + ["price"]
                df = df[cols]

            return df

        for split in ["train","validation","test"]:
            # 2.1) Leer el split crudo
            df_raw = pd.read_sql_table(split, con=engine_raw)
            logging.info(f"preprocess_data → {split}: {len(df_raw)} filas crudas")

            # 2.2) Preprocesar
            df_clean = _prep(df_raw)
            logging.info(f"preprocess_data → {split}: {len(df_clean)} filas limpias")

            # 2.3) Sobrescribir el split limpio
            with engine_clean.begin() as conn:
                df_clean.to_sql(
                    f"{split}_clean",
                    conn,
                    if_exists="replace",
                    index=False
                )
            logging.info(f"preprocess_data → {split}_clean actualizado con {len(df_clean)} filas")

    preprocess_task = PythonOperator(
        task_id="preprocess_data",
        python_callable=preprocess_data,
    )


    def train_and_register(**context):
        ti      = context["ti"]
        dag_run = context["dag_run"]

        # 1) Leer datos limpios desde CleanData
        CLEAN_URI = os.getenv("AIRFLOW_CONN_MYSQL_CLEAN")
        engine    = create_engine(CLEAN_URI)
        df_train  = pd.read_sql_table("train_clean",      con=engine)
        df_val    = pd.read_sql_table("validation_clean", con=engine)
        df_test   = pd.read_sql_table("test_clean",       con=engine)

        X_train, y_train = df_train.drop("price", axis=1), df_train["price"]
        X_val,   y_val   = df_val.drop("price", axis=1),   df_val["price"]
        X_test,  y_test  = df_test.drop("price", axis=1),  df_test["price"]

        logging.info(
            f"train_and_register → tamaños: "
            f"train={len(df_train)}, val={len(df_val)}, test={len(df_test)}"
        )

        # 2) Configurar MLflow
        mlflow.set_tracking_uri(os.getenv("AIRFLOW_VAR_MLFLOW_TRACKING_URI"))
        mlflow.set_experiment("Realtor_Price")

        # 3) Lista de alphas a probar
        alphas = [0.01, 0.1, 1.0, 10.0, 100.0]
        best_alpha    = None
        best_val_rmse = float("inf")

        # 4) Primera corrida: búsqueda manual de alpha
        with mlflow.start_run(run_name=f"train__{dag_run.run_id}") as run:
            current_run_id = run.info.run_id

            for α in alphas:
                m = Ridge(alpha=α).fit(X_train, y_train)
                rmse_val = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))

                mlflow.log_metric(f"val_rmse_alpha_{α}", rmse_val)

                if rmse_val < best_val_rmse:
                    best_val_rmse = rmse_val
                    best_alpha    = α

            # 5) Reentrenar con train+val usando best_alpha
            X_trval = np.vstack([X_train.values, X_val.values])
            y_trval = np.hstack([y_train.values, y_val.values])
            final_model = Ridge(alpha=best_alpha).fit(X_trval, y_trval)

            # 6) Evaluar en test
            test_rmse = np.sqrt(mean_squared_error(y_test, final_model.predict(X_test)))

            # 7) Log métricas y modelo final
            mlflow.log_metric("best_val_rmse", best_val_rmse)
            mlflow.log_metric("test_rmse",     test_rmse)
            mlflow.log_param( "best_alpha",    best_alpha)

            mlflow.sklearn.log_model(
                sk_model=final_model,
                artifact_path="model",
                registered_model_name="RealtorPriceModel"
            )

        # 8) Comparar test_rmse con el mejor run previo (excluyendo éste)
        exp = mlflow.get_experiment_by_name("Realtor_Price")
        best = mlflow.search_runs(
            [exp.experiment_id],
            filter_string=f"attributes.run_id != '{current_run_id}'",
            order_by=["metrics.test_rmse ASC"],
            max_results=1,
        )
        prev_best = best["metrics.test_rmse"].iloc[0] if not best.empty else None
        promoted  = (prev_best is None) or (test_rmse < prev_best)

        # 9) Reabrir el run actual y añadir tags
        mlflow.start_run(run_id=current_run_id)
        mlflow.set_tag("dag_run_id",         dag_run.run_id)
        mlflow.set_tag("execution_date",     context["execution_date"].isoformat())
        mlflow.set_tag("previous_best_rmse", str(prev_best))
        mlflow.set_tag("current_rmse",       str(test_rmse))
        mlflow.set_tag("promoted",           "true" if promoted else "false")
        mlflow.end_run()


        # 10) Si toca promover, hacerlo en el Model Registry
        if promoted:
            from mlflow.tracking import MlflowClient

            client = MlflowClient(
                tracking_uri=os.getenv("AIRFLOW_VAR_MLFLOW_TRACKING_URI")
            )

            # Recuperar todas las versiones del modelo y encontrar la generada en este run
            versions = client.get_latest_versions("RealtorPriceModel", stages=["None", "Staging", "Production"])
            model_version = None
            for mv in versions:
                if mv.run_id == current_run_id:
                    model_version = mv.version
                    break

            if model_version is None:
                raise RuntimeError(f"No pude encontrar la versión registrada para run_id={current_run_id}")

            # Transicionar al stage Production y archivar las anteriores
            client.transition_model_version_stage(
                name="RealtorPriceModel",
                version=model_version,
                stage="Production",
                archive_existing_versions=True
            )

            logging.info(
                f"train_and_register → Model version {model_version} "
                f"has been promoted to Production"
            )


        logging.info(
            f"train_and_register → run_id={current_run_id}  "
            f"best_alpha={best_alpha}  test_rmse={test_rmse:.2f}  promoted={promoted}"
        )


    train_task = PythonOperator(
        task_id="train_and_register",
        python_callable=train_and_register,
        provide_context=True,
    )

    # ruta alternativa cuando no entrenamos
    end_no_train = EmptyOperator(task_id="end_no_train")

    # ruta de reset, ahora bien definida
    end_after_reset = EmptyOperator(task_id="end_after_reset")

    # punto final común
    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

    # Flujo
    extract_task >> branch_exhaust

    # -- rama reset --
    branch_exhaust >> reset_task >> end_after_reset >> end

    # -- rama entrenamiento --
    branch_exhaust >> decide_task
    decide_task    >> split_task >> preprocess_task >> train_task >> end

    # -- rama no-train --
    decide_task    >> end_no_train >> end
