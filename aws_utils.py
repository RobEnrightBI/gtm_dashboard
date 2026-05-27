import io
import os
import re
import time

import boto3
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(r"C:\Users\REnright\Documents\Projects\.env")


# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────
AWS_REGION = "eu-west-2"

# S3
S3_BUCKET         = "boardintelligence-miscellaneous"
S3_DATA_PREFIX    = "soi_2026/data/"
S3_RESULTS_PREFIX = "soi_2026/athena-results/"

# Athena
S3_OUTPUT        = "s3://boardintelligence-query-results/queries_folder/"
WORKGROUP        = "primary"
DEFAULT_DATABASE = "curated_data"

# Data mart tables available in S3
TABLES = [
    "dim_directors",
    "dim_companies",
    "fact_board_seats",
    "connections",
    "target_summary",
]

# Default path to data_marts.xlsx — override as needed
DATA_MARTS_PATH = Path(__file__).parent / "data_marts" / "data_marts.xlsx"


# ──────────────────────────────────────────────
# CLIENT FACTORIES
# ──────────────────────────────────────────────
def _session() -> boto3.Session:
    return boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS"),
        region_name=AWS_REGION,
    )


def get_s3_client():
    return _session().client("s3")


def get_athena_client():
    return _session().client("athena")


# ──────────────────────────────────────────────
# SAFETY VALIDATOR (Athena — read-only guard)
# ──────────────────────────────────────────────
FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "MERGE", "REPLACE", "RENAME", "GRANT", "REVOKE",
]


def _validate_query(query: str) -> None:
    """Block any non-SELECT queries before they reach AWS."""
    cleaned = " ".join(
        line for line in query.upper().splitlines()
        if not line.strip().startswith("--")
    )
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", cleaned):
            raise ValueError(
                f"Blocked: Query contains forbidden keyword '{keyword}'.\n"
                f"This utility is read-only. Only SELECT queries are permitted."
            )
    if not re.search(r"\bSELECT\b", cleaned):
        raise ValueError(
            "Blocked: Only SELECT queries are permitted.\n"
            "This utility is read-only and will not modify any AWS data."
        )


# ──────────────────────────────────────────────
# ATHENA QUERY FUNCTIONS
# ──────────────────────────────────────────────
def run_query(query: str, database: str = DEFAULT_DATABASE) -> pd.DataFrame:
    """
    Run an Athena SQL query and return results as a DataFrame.

    Args:
        query:    SQL SELECT query string
        database: Athena database to query (defaults to DEFAULT_DATABASE)

    Returns:
        pd.DataFrame with query results

    Example:
        df = run_query("SELECT * FROM my_table LIMIT 100")
        df = run_query("SELECT * FROM my_table", database="curated_salesforce")
    """
    _validate_query(query)
    client = get_athena_client()

    response = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": S3_OUTPUT},
        WorkGroup=WORKGROUP,
    )
    query_id = response["QueryExecutionId"]
    print(f"Running query... (ID: {query_id})")

    while True:
        status = client.get_query_execution(QueryExecutionId=query_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            print("Query succeeded")
            break
        elif state in ["FAILED", "CANCELLED"]:
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
            raise Exception(f"Query {state}: {reason}")
        print("  Waiting for results...")
        time.sleep(2)

    rows = []
    columns = None
    paginator = client.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=query_id):
        if columns is None:
            columns = [col["Label"] for col in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
        data_rows = page["ResultSet"]["Rows"][1:] if not rows else page["ResultSet"]["Rows"]
        for row in data_rows:
            rows.append([col.get("VarCharValue", "") for col in row["Data"]])

    df = pd.DataFrame(rows, columns=columns)
    print(f"Returned {len(df):,} rows, {len(df.columns)} columns")
    return df


def list_databases() -> list:
    """List all available Athena databases."""
    client = get_athena_client()
    response = client.list_databases(CatalogName="AwsDataCatalog")
    databases = [db["Name"] for db in response["DatabaseList"]]
    print("Available databases:")
    for db in databases:
        print(f"  - {db}")
    return databases


def list_tables(database: str = DEFAULT_DATABASE) -> list:
    """List all tables in a given Athena database."""
    client = get_athena_client()
    response = client.list_table_metadata(
        CatalogName="AwsDataCatalog",
        DatabaseName=database,
    )
    tables = [t["Name"] for t in response["TableMetadataList"]]
    print(f"Tables in '{database}':")
    for t in tables:
        print(f"  - {t}")
    return tables


def preview_table(table: str, database: str = DEFAULT_DATABASE, limit: int = 10) -> pd.DataFrame:
    """
    Quick preview of any Athena table.

    Args:
        table:    Table name
        database: Database name (defaults to DEFAULT_DATABASE)
        limit:    Number of rows to return (default 10)
    """
    return run_query(f'SELECT * FROM "{database}"."{table}" LIMIT {limit}', database=database)


# ──────────────────────────────────────────────
# S3 DATA LOADING
# ──────────────────────────────────────────────
def load_table(table_name: str) -> pd.DataFrame:
    """
    Load a data mart table directly from S3 Parquet.

    Args:
        table_name: One of the names in TABLES

    Returns:
        pd.DataFrame
    """
    if table_name not in TABLES:
        raise ValueError(f"Unknown table '{table_name}'. Available: {TABLES}")
    key = f"{S3_DATA_PREFIX}{table_name}/{table_name}.parquet"
    obj = get_s3_client().get_object(Bucket=S3_BUCKET, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


# ──────────────────────────────────────────────
# DATA MART EXCEL LOADING
# ──────────────────────────────────────────────
def load_data_marts(path: Path = DATA_MARTS_PATH) -> dict[str, pd.DataFrame]:
    """
    Read all sheets from data_marts.xlsx, returning {sheet_name: DataFrame}.
    Column names are normalised (spaces replaced with underscores).
    """
    xl = pd.ExcelFile(path)
    sheets = {sheet: xl.parse(sheet) for sheet in xl.sheet_names}
    for df in sheets.values():
        df.columns = [c.replace(" ", "_") for c in df.columns]
    print(f"OK Loaded {len(sheets)} sheets from {path.name}")
    return sheets


# ──────────────────────────────────────────────
# S3 PUSH UTILITIES
# ──────────────────────────────────────────────
def _sanitise(df: pd.DataFrame) -> pd.DataFrame:
    """Convert pandas extension types to standard numpy types for Parquet compatibility."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_period_dtype(df[col]):
            df[col] = df[col].dt.to_timestamp()
        elif hasattr(df[col].dtype, "numpy_dtype"):
            df[col] = df[col].astype(df[col].dtype.numpy_dtype)
        elif df[col].dtype == object:
            df[col] = df[col].astype(str)
    return df


def push_df(df: pd.DataFrame, name: str, s3=None) -> None:
    """Upload a single DataFrame to S3 as Parquet under its own subfolder."""
    if s3 is None:
        s3 = get_s3_client()
    key = f"{S3_DATA_PREFIX}{name}/{name}.parquet"
    buf = io.BytesIO()
    _sanitise(df).to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=buf.getvalue())
    print(f"  OK {name}.parquet -> s3://{S3_BUCKET}/{key}")


def push_all(sheets: dict[str, pd.DataFrame]) -> None:
    """Upload all sheets to S3 as Parquet."""
    s3 = get_s3_client()
    for name, df in sheets.items():
        push_df(df, name, s3=s3)
    print("All tables pushed.")


def delete_flat_files(names: list[str] = TABLES) -> None:
    """Delete any legacy flat parquet files (pre-subfolder structure)."""
    s3 = get_s3_client()
    for name in names:
        key = f"{S3_DATA_PREFIX}{name}.parquet"
        s3.delete_object(Bucket=S3_BUCKET, Key=key)
        print(f"  OK Deleted s3://{S3_BUCKET}/{key}")


# ──────────────────────────────────────────────
# ENTRYPOINT — push all data marts to S3
# ──────────────────────────────────────────────
if __name__ == "__main__":
    sheets = load_data_marts()
    push_all(sheets)
