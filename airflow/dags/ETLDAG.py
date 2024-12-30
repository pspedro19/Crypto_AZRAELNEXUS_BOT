"""
sDAG para el procesamiento ETL de datos de telemetría del FACSAT-2
"""
import boto3
from botocore.config import Config
from io import BytesIO
import logging
from datetime import datetime, timedelta
import time
from airflow import DAG
from airflow.operators.python import PythonOperator
from pymongo import MongoClient
import polars as pl
import os
import warnings
from typing import List, Dict, Any, Union

# Ignore warnings
warnings.filterwarnings("ignore")

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(funcName)s:%(lineno)d",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "etl_process.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)



class MinioConfig:
    def __init__(self):
        self.endpoint_url = os.getenv('AWS_ENDPOINT_URL_S3', 'http://minio:9000')
        self.access_key = os.getenv('AWS_ACCESS_KEY_ID', 'minio')
        self.secret_key = os.getenv('AWS_SECRET_ACCESS_KEY', 'minio123')
        self.bucket_name = 'data'

    def get_client(self):
        # Create a configuration object using botocore.config.Config
        s3_config = Config(
            signature_version='s3v4'
        )
        
        return boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=s3_config,
            region_name='us-east-1'
        )

def upload_to_minio(df: pl.DataFrame, filename: str, minio_config: MinioConfig):
    """
    Sube un DataFrame a MinIO en formato CSV
    """
    try:
        # Crear un buffer temporal en memoria
        csv_buffer = BytesIO()
        df.write_csv(csv_buffer, float_precision=2)
        csv_buffer.seek(0)

        # Obtener cliente de MinIO
        s3_client = minio_config.get_client()

        # Subir el archivo
        s3_client.upload_fileobj(
            csv_buffer,
            minio_config.bucket_name,
            os.path.basename(filename),  # Use just the filename, not the full path
            ExtraArgs={'ContentType': 'text/csv'}
        )
        
        logger.info(f"Successfully uploaded {filename} to MinIO bucket {minio_config.bucket_name}")
    
    except Exception as e:
        logger.error(f"Error uploading to MinIO: {str(e)}")
        raise



def get_project_paths():
    """
    Configura las rutas del proyecto de manera centralizada.
    """
    # Directorio base del proyecto (ruta absoluta al directorio dags)
    dags_dir = "/opt/airflow/dags"
    
    # Ruta al directorio de MinIO
    minio_data_dir = "/opt/minio/data"  # Esta será mapeada al directorio real
    
    paths = {
        'dictionary_path': os.path.join(dags_dir, 'diccionario_de_datos.csv'),
        'minio_data': minio_data_dir,
    }
    
    # Log the paths for debugging
    logger.info(f"Dictionary path: {paths['dictionary_path']}")
    logger.info(f"MinIO data path: {paths['minio_data']}")
    
    return paths



class MongoDBConfig:
    def __init__(self):
        logger.info("Initializing MongoDB configuration")
        # Usar el nombre del servicio definido en docker-compose
        self.host = os.getenv("MONGO_SECONDARY_IP", "mongo-secondary")
        self.port = int(os.getenv("MONGO_PORT", "27017"))
        self.database = os.getenv("MONGO_DATABASE", "facsat2")
        self.replica_set = os.getenv("REPLICA_SET", "rs0")
        
        # Log configuration for debugging
        logger.info(f"MongoDB Config - Host: {self.host}, Port: {self.port}, DB: {self.database}, RS: {self.replica_set}")
        
        # Connection options
        self.options = {
            'serverSelectionTimeoutMS': 30000,
            'connectTimeoutMS': 30000,
            'socketTimeoutMS': 45000,
            'retryWrites': True,
            'retryReads': True,
            'maxPoolSize': 50
        }

    @property
    def uri(self) -> str:
        # Construct basic URI
        uri = f"mongodb://{self.host}:{self.port}/{self.database}"
        logger.info(f"Generated MongoDB URI: {uri}")
        return uri


def extract_data(collection: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Executes a MongoDB query with improved error handling and retry logic.
    """
    retries = 3
    retry_delay = 5
    client = None

    for attempt in range(retries):
        try:
            mongodb_config = MongoDBConfig()
            logger.info(f"Attempting MongoDB connection (attempt {attempt + 1}/{retries})")
            
            # Create client with connection timeout
            client = MongoClient(mongodb_config.uri)
            
            # Test connection with timeout
            client.admin.command("ping")
            logger.info("Successfully connected to MongoDB")
            
            # Use the correct database and collection
            db = client[mongodb_config.database]
            collection_obj = db["ParamData_Latest"]  # Use the passed collection name
            
            query = kwargs.get("query", {})
            projection = kwargs.get("projection", {})
            skip = kwargs.get("skip", 0)
            limit = kwargs.get("limit", 0)
            
            logger.info(f"Executing query on collection {collection}: {query}")
            result = collection_obj.find(query, projection).skip(skip).limit(limit)
            data = list(result)
            
            logger.info(f"Successfully retrieved {len(data)} documents")
            return data

        except Exception as e:
            logger.error(f"MongoDB connection attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("All connection attempts failed")
                raise Exception(f"Failed to connect to MongoDB after {retries} attempts: {str(e)}")
        
        finally:
            if client:
                client.close()
                logger.debug("MongoDB connection closed")

def crear_dataframe_polars(data: List[Dict[str, Any]], system: str, table: str) -> pl.DataFrame:
    """
    Creates a DataFrame from JSON telemetry data using Polars for improved performance.
    """
    try:
        if not data:
            raise ValueError("Input data is empty")

        df = pl.json_normalize(data)

        if df.is_empty():
            raise ValueError("DataFrame is empty")

        required_columns = {"Ts", "Val", "Param.Name", "Param.Table"}
        missing_columns = required_columns - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        df = df.with_columns([pl.col("Ts").cast(pl.Int64).map_elements(datetime.fromtimestamp).alias("Date")])

        has_index = "Param.Index" in df.columns

        if has_index:
            df = df.with_columns(
                [
                    pl.when(pl.col("Param.Index").is_not_null())
                    .then(pl.col("Param.Index") + 1)
                    .otherwise(pl.lit(0))
                    .alias("Param.Index")
                    .cast(pl.Int64)
                ]
            )

            final_df = df.pivot(
                values="Val", index="Date", columns=["Param.Name", "Param.Index"], aggregate_function="first"
            )

            old_columns = [col for col in final_df.columns if col != "Date"]
            new_columns = {}
            for col in old_columns:
                parts = col.strip("{}").split(",")
                param_name = parts[0].strip('"')
                index = int(parts[1].strip())
                new_name = (
                    f"{system}{str(table)}_{param_name}"
                    if index == 0
                    else f"{system}{str(table)}_{param_name}_{str(int(index))}"
                )
                new_columns[col] = new_name

        else:
            final_df = df.pivot(values="Val", index="Date", columns="Param.Name", aggregate_function="first")
            new_columns = {col: f"{system}{str(table)}_{col}" for col in final_df.columns if col != "Date"}

        final_df = final_df.rename(new_columns)
        return final_df

    except Exception as e:
        error_msg = f"Error processing telemetry data: {str(e)}"
        print(error_msg)
        raise RuntimeError(error_msg) from e


def check_columns_missmatch(dataframes: List[pl.DataFrame]) -> List[pl.DataFrame]:
    """
    Optimized function to align columns and data types in Polars DataFrames.
    """
    if not dataframes:
        return []

    schemas = {col: dtype for df in dataframes for col, dtype in df.schema.items()}
    final_schema = {}
    for col in schemas:
        types = [df.schema.get(col) for df in dataframes if col in df.columns]
        final_schema[col] = pl.Float64 if pl.Int64 in types and pl.Float64 in types else types[0]

    def align_dataframe(df: pl.DataFrame) -> pl.DataFrame:
        expressions = []

        for col, target_type in final_schema.items():
            if col in df.columns:
                if df.schema[col] != target_type:
                    expressions.append(pl.col(col).cast(target_type).alias(col))
            else:
                expressions.append(pl.lit(None).cast(target_type).alias(col))

        return df.with_columns(expressions) if expressions else df

    return list(map(align_dataframe, dataframes))


def clean_data_with_flexible_references(data_df: pl.DataFrame, ref_df: pl.DataFrame) -> pl.DataFrame:
    """
    Cleans data based on flexible references for invalid and valid values.
    """
    def clean_column(col_name: str, col_refs: pl.DataFrame) -> pl.Expr:
        if col_refs.is_empty():
            return pl.col(col_name)

        invalid_value = col_refs.get_column("Invalido").item() if not col_refs.is_empty() else None

        if not col_refs.is_empty():
            valid_values = col_refs.select(
                pl.col("Valido")
                .str.extract_all(r"(\d+)")
                .list.eval(pl.element().cast(pl.Int64))
            ).item()
        else:
            valid_values = None

        invalid_condition = pl.col(col_name) == invalid_value if invalid_value is not None else pl.lit(False)
        valid_condition = pl.col(col_name).is_in(valid_values) if valid_values is not None else pl.lit(True)
        final_condition = ~(invalid_condition | ~valid_condition)

        return pl.when(final_condition).then(pl.col(col_name)).otherwise(None).alias(col_name)

    return data_df.select(
        [clean_column(col_name, ref_df.filter(pl.col("Variable") == col_name)) for col_name in data_df.columns]
    )


def remove_full_null_rows(df: pl.DataFrame) -> pl.DataFrame:
    """
    Remove rows from a Polars DataFrame where all columns (except 'Date') contain null values.
    """
    cols_to_check = [col for col in df.columns if col != "Date"]
    mask = df.select(pl.any_horizontal(~pl.col(cols_to_check).is_null())).to_series()
    return df.filter(mask)


def run_etl_process(
    batch_size: int = 500000,
    dictionary_path: str = None,
    bucket_path: str = None,
) -> None:
    """
    Process MongoDB data using Polars for improved performance.
    """
    try:
        # Obtener las rutas del proyecto
        paths = get_project_paths()
        
        # Usar las rutas proporcionadas o las predeterminadas
        dictionary_path = dictionary_path or paths['dictionary_path']
        bucket_path = bucket_path or paths['minio_data']
        
        logger.info(f"Using dictionary path: {dictionary_path}")
        logger.info(f"Using bucket path: {bucket_path}")

        # Create MinioConfig instance
        minio_config = MinioConfig()

        # Asegurar que el directorio de salida existe
        os.makedirs(bucket_path, exist_ok=True)

        dic_datos = pl.read_csv(dictionary_path)
        
        dic_datos = dic_datos.with_columns(
            [
                pl.when(pl.col("Indice") >= 0)
                .then(pl.col("Indice") + 1)
                .otherwise(pl.lit(0))
                .cast(pl.Int64)
                .alias("Indice")
            ]
        )

        dic_datos = dic_datos.with_columns(
            [
                pl.when(pl.col("Indice") > 0)
                .then(
                    pl.col("Sistema")
                    + pl.col("Tabla").cast(pl.String)
                    + "_"
                    + pl.col("Variable")
                    + "_"
                    + pl.col("Indice").cast(pl.Int64).cast(pl.Utf8)
                )
                .otherwise(pl.col("Sistema") + pl.col("Tabla").cast(pl.String) + "_" + pl.col("Variable"))
                .alias("Variable")
            ]
        )

        loop_over_nodes = (
            dic_datos.group_by(["Sistema", "Nodo", "Tabla"]).agg(pl.col("Indice").mean()).sort(["Nodo", "Tabla"])
        )

        for row in loop_over_nodes.iter_rows(named=True):
            sistema = row["Sistema"]
            num_nodo = row["Nodo"]
            num_tabla = row["Tabla"]

            logger.info(f"Processing Node {sistema}: {num_nodo}, Table # {num_tabla}")

            skip_count = 0
            node_data_frames = []
            combined_node_df = pl.DataFrame()

            while True:
                node_dict = extract_data(
                    collection="ParamData",
                    query={"Param.Node": num_nodo, "Param.Table": num_tabla},
                    limit=batch_size,
                    skip=skip_count,
                )

                if not node_dict:
                    break

                try:
                    node_df = crear_dataframe_polars(node_dict, sistema, num_tabla)
                    node_data_frames.append(node_df)
                except Exception as e:
                    logger.error(f"Error processing batch for Node {num_nodo}, Table {num_tabla}: {str(e)}")
                    continue

                skip_count += batch_size

            if node_data_frames:
                node_data_frames_checked = check_columns_missmatch(node_data_frames)
                combined_node_df = pl.concat(
                    [df.select(node_data_frames_checked[0].columns) for df in node_data_frames_checked]
                )

                if not combined_node_df.is_empty():
                    combined_node_df = combined_node_df.sort("Date")
                    numeric_cols = [col for col in combined_node_df.columns if col not in ["Date", "Tabla"]]
                    combined_node_df = combined_node_df.with_columns([pl.col(numeric_cols).cast(pl.Float32)])

                    cleaned_node_df = clean_data_with_flexible_references(combined_node_df, dic_datos)
                    fully_cleaned_node_df = remove_full_null_rows(cleaned_node_df)

                    output_path = os.path.join(bucket_path, f"{sistema}_{num_tabla}_collection.csv")
                    fully_cleaned_node_df.write_csv(output_path, float_precision=2, batch_size=batch_size)
                    
                    # Use the created minio_config instance
                    upload_to_minio(fully_cleaned_node_df, output_path, minio_config)
                    
                    logger.info(f"Successfully wrote data to {output_path}")
                    logger.info(f"Final DataFrame shape: {fully_cleaned_node_df.shape}")
                    logger.info(f"Memory usage: {fully_cleaned_node_df.estimated_size() / 1024 / 1024:.2f} MB")

    except Exception as e:
        logger.error(f"Error in data processing pipeline: {str(e)}")
        raise


def check_mongodb_connection():
    """Verifica la conexión a MongoDB antes de iniciar el ETL"""
    try:
        mongodb_config = MongoDBConfig()
        with MongoClient(mongodb_config.uri) as client:
            client.admin.command("ping")
        logger.info("MongoDB connection check successful")
    except Exception as e:
        logger.error(f"MongoDB connection check failed: {str(e)}")

# Obtener las rutas del proyecto
paths = get_project_paths()

# DAG definition
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'email': ['admin@example.com'],
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=15)
}

with DAG(
    dag_id="etl_telemetry_facsat2",
    description="DAG para procesar datos de telemetría del FACSAT-2",
    schedule_interval=None,  # Set to None for manual triggering
    start_date=datetime(2023, 1, 1),
    default_args=default_args,
    catchup=False,
    tags=["etl", "facsat2"],
) as dag:
    
    # Task de verificación de conexión a MongoDB
    connection_check = PythonOperator(
        task_id='check_mongodb_connection',
        python_callable=check_mongodb_connection,
        dag=dag
    )
    
    # Task principal de ETL
    run_etl_task = PythonOperator(
        task_id="run_etl_process",
        python_callable=run_etl_process,
        op_kwargs={
            "batch_size": 500000,
            "dictionary_path": paths['dictionary_path'],
            "bucket_path": paths['minio_data'],
        },
    )

    # Definir el orden de ejecución
    connection_check >> run_etl_task
