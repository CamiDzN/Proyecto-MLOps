import os
import datetime
import requests
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
import mlflow
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
        """ Llama a restart_data_generation y limpia todas las tablas. """
        RAW_URI = os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT")
        CLEAN_URI = os.getenv("AIRFLOW_CONN_MYSQL_CLEAN")
        engine_raw = create_engine(RAW_URI)
        engine_clean = create_engine(CLEAN_URI)

        # Llamada al endpoint de reinicio
        params = {"group_number": 7, "day": "Tuesday"}
        r = requests.get("http://10.43.101.108:80/restart_data_generation", params=params)
        r.raise_for_status()

        # Limpiar tablas en RawData
        tablas_raw = ["realtor_raw", "train", "validation", "test"]
        with engine_raw.begin() as conn:
            for t in tablas_raw:
                conn.execute(text(f"TRUNCATE TABLE `{t}`"))

        # Limpiar tablas en CleanData
        tablas_clean = ["train_clean", "validation_clean", "test_clean"]
        with engine_clean.begin() as conn:
            for t in tablas_clean:
                conn.execute(text(f"TRUNCATE TABLE `{t}`"))

    reset_task = PythonOperator(
        task_id="reset_data",
        python_callable=reset_data,
    )

    def decide_train(**context):
        """
        - Extrae las últimas `new_records` de realtor_raw.
        - Verifica que estén todas las columnas esperadas.
        - Verifica rangos plausibles para cada variable.
        - Registra en MLflow decisión y motivo.
        """
        ti = context["ti"]
        new_records = ti.xcom_pull(key="new_records", task_ids="extract_data") or 0

        # 1) Conectar a RawData y leer las últimas filas
        RAW_URI = os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT")
        engine = create_engine(RAW_URI)
        if new_records > 0:
            df = pd.read_sql_query(
                """
                SELECT * FROM realtor_raw
                ORDER BY fetched_at DESC
                LIMIT :n
                """,
                con=engine,
                params={"n": new_records},
            )
        else:
            df = pd.DataFrame()

        # 2) Validar presencia de columnas
        required_cols = {
            "brokered_by", "status", "price", "bed", "bath",
            "acre_lot", "street", "city", "state",
            "zip_code", "house_size", "prev_sold_date"
        }
        missing = required_cols - set(df.columns)
        invalid_reasons = []

        if missing:
            invalid_reasons.append(f"Faltan columnas: {sorted(missing)}")

        # 3) Validar no nulos en todas las columnas
        null_counts = df[required_cols].isnull().sum()
        null_cols = null_counts[null_counts > 0].index.tolist()
        if null_cols:
            invalid_reasons.append(f"Nulos en: {null_cols}")

        # 4) Validar rangos aproximados
        if not df.empty:
            # price > 0
            if (df["price"] <= 0).any():
                invalid_reasons.append("Price ≤ 0 en alguna fila")
            # beds y baths enteros ≥ 0 y ≤ 10
            bad_bed = df[~df["bed"].apply(float.is_integer) | (df["bed"] < 0) | (df["bed"] > 10)]
            if not bad_bed.empty:
                invalid_reasons.append("bed fuera de [0–10] o no entero")
            bad_bath = df[~df["bath"].apply(float.is_integer) | (df["bath"] < 0) | (df["bath"] > 10)]
            if not bad_bath.empty:
                invalid_reasons.append("bath fuera de [0–10] o no entero")
            # acre_lot > 0 y < 1000
            if ((df["acre_lot"] <= 0) | (df["acre_lot"] > 10000)).any():
                invalid_reasons.append("acre_lot fuera de (0,10000]")
            # house_size > 0
            if (df["house_size"] <= 0).any():
                invalid_reasons.append("house_size ≤ 0")
            # status en {'a','b'}
            if ~df["status"].isin(["a", "b"]).all():
                invalid_reasons.append("status no en {'a','b'}")
            # zip_code como cadena de longitud ≥5
            bad_zip = df[~df["zip_code"].astype(str).str.match(r"^\d{5,}$")]
            if not bad_zip.empty:
                invalid_reasons.append("zip_code inválido")
            # prev_sold_date parseable
            try:
                pd.to_datetime(df["prev_sold_date"])
            except Exception:
                invalid_reasons.append("prev_sold_date no parseable")

        # 5) Decidir y registrar en MLflow
        mlflow_uri = os.getenv("AIRFLOW_VAR_MLFLOW_TRACKING_URI")
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment("Realtor_Price")

        with mlflow.start_run(run_name="decision"):
            mlflow.log_metric("new_records", new_records)
            if invalid_reasons:
                decision = "no_train"
                reason = " & ".join(invalid_reasons)
            elif new_records > 100:
                decision = "train"
                reason = f"{new_records} nuevos > 100"
            else:
                decision = "no_train"
                reason = f"{new_records} nuevos ≤ 100"

            mlflow.set_tag("decision", decision)
            mlflow.set_tag("reason", reason)

        return decision

    decide_task = BranchPythonOperator(
        task_id="decide_to_train",
        python_callable=decide_train,
        provide_context=True,
    )

    def split_data():
        """
        Lee realtor_raw de RawData, lo mezcla aleatoriamente y lo divide:
        60% train, 20% val, 20% test. Escribe en tres tablas en la misma BD.
        """
        RAW_URI = os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT")
        engine = create_engine(RAW_URI)

        df = pd.read_sql_table("realtor_raw", con=engine).sample(frac=1, random_state=42)
        n = len(df)
        train_df = df.iloc[: int(0.6 * n)]
        val_df = df.iloc[int(0.6 * n) : int(0.8 * n)]
        test_df = df.iloc[int(0.8 * n) :]

        with engine.begin() as conn:
            train_df.to_sql("train", conn, if_exists="replace", index=False)
            val_df.to_sql("validation", conn, if_exists="replace", index=False)
            test_df.to_sql("test", conn, if_exists="replace", index=False)

    split_task = PythonOperator(
        task_id="split_data",
        python_callable=split_data,
    )

    def preprocess_data():
        """
        Toma Train/Val/Test de RawData y aplica un preprocessing simple:
        - forward-fill y fillna(0)
        - one-hot encoding de categóricas
        Almacena en CleanData tablas train_clean, validation_clean, test_clean.
        """
        RAW_URI = os.getenv("AIRFLOW_CONN_MYSQL_DEFAULT")
        CLEAN_URI = os.getenv("AIRFLOW_CONN_MYSQL_CLEAN")
        engine_raw = create_engine(RAW_URI)
        engine_clean = create_engine(CLEAN_URI)

        def _prep(df):
            df = df.fillna(method="ffill").fillna(0)
            cat_cols = df.select_dtypes(include=["object"]).columns
            return pd.get_dummies(df, columns=cat_cols, drop_first=True)

        for name in ["train", "validation", "test"]:
            df = pd.read_sql_table(name, con=engine_raw)
            df_clean = _prep(df)
            with engine_clean.begin() as conn:
                df_clean.to_sql(f"{name}_clean", conn, if_exists="replace", index=False)

    preprocess_task = PythonOperator(
        task_id="preprocess_data",
        python_callable=preprocess_data,
    )

    def train_and_register():
        """
        Entrena un LinearRegression sobre clean data, evalúa RMSE en Val/Test,
        compara con el mejor run anterior en MLflow y promueve si mejora.
        """
        CLEAN_URI = os.getenv("AIRFLOW_CONN_MYSQL_CLEAN")
        engine = create_engine(CLEAN_URI)

        df_train = pd.read_sql_table("train_clean", con=engine)
        df_val = pd.read_sql_table("validation_clean", con=engine)
        df_test = pd.read_sql_table("test_clean", con=engine)

        X_train, y_train = df_train.drop("price", axis=1), df_train["price"]
        X_val, y_val = df_val.drop("price", axis=1), df_val["price"]
        X_test, y_test = df_test.drop("price", axis=1), df_test["price"]

        mlflow_uri = os.getenv("AIRFLOW_VAR_MLFLOW_TRACKING_URI")
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment("Realtor_Price")

        with mlflow.start_run(run_name="train"):
            model = LinearRegression().fit(X_train, y_train)
            val_rmse = np.sqrt(mean_squared_error(y_val, model.predict(X_val)))
            test_rmse = np.sqrt(mean_squared_error(y_test, model.predict(X_test)))

            mlflow.log_metric("val_rmse", val_rmse)
            mlflow.log_metric("test_rmse", test_rmse)
            mlflow.sklearn.log_model(model, "model")

            # buscar el mejor run previo
            exp = mlflow.get_experiment_by_name("Realtor_Price")
            best = mlflow.search_runs(
                [exp.experiment_id], order_by=["metrics.test_rmse ASC"], max_results=1
            )
            best_rmse = best["metrics.test_rmse"][0] if not best.empty else None

            if best_rmse is None or test_rmse < best_rmse:
                mlflow.set_tag("promoted", "true")
            else:
                mlflow.set_tag("promoted", "false")

            mlflow.set_tag("previous_best_rmse", str(best_rmse))
            mlflow.set_tag("current_rmse", str(test_rmse))

    train_task = PythonOperator(
        task_id="train_and_register",
        python_callable=train_and_register,
    )

    # ruta alternativa cuando no entrenamos
    end_no_train = EmptyOperator(task_id="end_no_train")

    # punto final común
    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

# Flujo
    extract_task >> branch_exhaust
    branch_exhaust >> reset_task >> EmptyOperator(task_id="end_after_reset")
    branch_exhaust >> decide_task  
    decide_task >> split_task >> preprocess_task >> train_task >> end
    decide_task >> end_no_train >> end
