"""Amazon Merge Upsert Module which can upsert existing table (PRIVATE)."""

import logging
from typing import List

import pandas

import awswrangler as wr

logging.basicConfig(level=logging.INFO, format="[%(name)s][%(funcName)s] %(message)s")
logging.getLogger("awswrangler").setLevel(logging.DEBUG)
logging.getLogger("botocore.credentials").setLevel(logging.CRITICAL)
_logger: logging.Logger = logging.getLogger(__name__)


def _update_existing_table(
    existing_df: pandas.DataFrame, delta_df: pandas.DataFrame, primary_key: List[str], database: str, table: str
) -> None:
    """Perform Update else Insert onto an existing Glue table """
    # Set Index on the pandas dataframe so that join/concat can be made
    existing_df = existing_df.set_index(keys=primary_key, drop=False, verify_integrity=True)
    delta_df = delta_df.set_index(keys=primary_key, drop=False, verify_integrity=True)
    # Merge-Upsert the data for both of the dataframe
    merged_df = pandas.concat([existing_df[~existing_df.index.isin(delta_df.index)], delta_df])
    # Remove the index and drop the index columns
    merged_df = merged_df.reset_index(drop=True)
    # Get existing tables location
    path = wr.catalog.get_table_location(database=database, table=table)
    # Write to Glue catalog
    response = wr.s3.to_parquet(df=merged_df, path=path, dataset=True, database=database, table=table, mode="overwrite")
    _logger.info(f"Successfully Upserted {database}.{table} and got response as {str(response)}")


def _is_data_quality_sufficient(
    existing_df: pandas.DataFrame, delta_df: pandas.DataFrame, primary_key: List[str]
) -> bool:
    """Check data quality of existing table and the new delta feed"""
    error_messages = list()
    # Check for duplicates on the primary key in the existing table
    if sum(pandas.DataFrame(existing_df, columns=primary_key).duplicated()) != 0:
        error_messages.append("Data inside the existing table has duplicates.")
    # Check for duplicates in the delta dataframe
    if sum(pandas.DataFrame(delta_df, columns=primary_key).duplicated()) != 0:
        error_messages.append("Data inside the delta dataframe has duplicates.")
    if (
        existing_df.shape[1] != delta_df.shape[1]
        or len(existing_df.columns.intersection(delta_df.columns)) != existing_df.shape[1]
    ):
        error_messages.append(
            f"Column names or number of columns mismatch! \n Columns in delta_df {delta_df.columns}.\n  Columns in "
            f"existing_df is {existing_df.columns} "
        )
    # Return True only if no errors are encountered
    return len(error_messages) == 0


def merge_upsert_table(delta_df: pandas.DataFrame, database: str, table: str, primary_key: List[str]) -> None:
    """Perform Upsert (Update else Insert) onto an existing Glue table"""
    # Check if table exists first
    if wr.catalog.does_table_exist(database=database, table=table):
        # Read the existing table into a pandas dataframe
        existing_df = wr.s3.read_parquet_table(database=database, table=table)
        # Check if data quality inside dataframes to be merged are sufficient
        if _is_data_quality_sufficient(existing_df=existing_df, delta_df=delta_df, primary_key=primary_key) is True:
            # If data quality is sufficient then merge upsert the table
            _update_existing_table(
                existing_df=existing_df, delta_df=delta_df, primary_key=primary_key, database=database, table=table
            )
    elif wr.catalog.does_table_exist(database=database, table=table) is False:
        _logger.exception(f"database_name.table_name= {database}.{table} does not exist ")
    else:
        _logger.exception("Reached a unknown logical state")