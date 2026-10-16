import argparse
import logging
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv


# Load configuration from the .env file beside this script.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_SCHEMA = os.getenv("PG_SCHEMA", "public")


def get_output_dir():
    """Return output directory from env or create and return an 'output' folder in cwd."""
    raw_dir = (os.getenv("OUTPUT_DIR") or "").strip()
    if raw_dir:
        output_dir = Path(raw_dir)
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
    else:
        output_dir = Path.cwd() / "output"

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def setup_logger(zip_stem):
    """Configure logging to both a file in 'logs' folder and console."""
    logs_dir = Path.cwd() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    date_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{zip_stem}_{date_time}.logs"
    log_file_path = logs_dir / log_filename

    logger = logging.getLogger("PostgresCSVExporter")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger, log_file_path


def parse_table_list(raw_items):
    """Parse comma- or whitespace-separated table names from strings or lists."""
    if not raw_items:
        return []
    if isinstance(raw_items, str):
        raw_items = [raw_items]

    tables = []
    for item in raw_items:
        if not item:
            continue
        parts = [p.strip() for p in re.split(r"[\s,]+", item.strip()) if p.strip()]
        tables.extend(parts)
    return tables


def resolve_tables(cli_tables, env_tables_str):
    """Resolve table list prioritizing CLI arguments, then .env, then interactive prompt."""
    tables = parse_table_list(cli_tables)
    if not tables and env_tables_str:
        tables = parse_table_list(env_tables_str)

    if not tables:
        try:
            user_input = input(
                "Enter table name(s) to export (separated by comma or space): "
            ).strip()
            tables = parse_table_list(user_input)
        except (EOFError, KeyboardInterrupt):
            print("\nExport cancelled.", file=sys.stderr)
            sys.exit(1)

    return tables


def resolve_zip_name(cli_zip_name, env_zip_name, default_prefix="export"):
    """Resolve zip filename prioritizing CLI arguments, then .env, then interactive prompt, then timestamped default."""
    zip_name = (cli_zip_name or "").strip()
    if not zip_name:
        zip_name = (env_zip_name or "").strip()

    if not zip_name:
        try:
            user_input = input(
                "Enter zip file/folder name (press Enter for timestamped default): "
            ).strip()
            if user_input:
                zip_name = user_input
        except (EOFError, KeyboardInterrupt):
            print("\nExport cancelled.", file=sys.stderr)
            sys.exit(1)

    if not zip_name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"{default_prefix}_{timestamp}"

    # Ensure .zip extension and strip any directory traversal
    if not zip_name.lower().endswith(".zip"):
        zip_name = f"{zip_name}.zip"

    return Path(zip_name).name


def create_zip_archive(output_dir, zip_filename, file_paths):
    """Compress the exported CSV files into a zip archive inside output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / zip_filename

    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            zf.write(file_path, arcname=file_path.name)

    return zip_path


def parse_table_name(table_name):
    """Accept table_name or schema.table_name."""
    parts = table_name.split(".")

    if len(parts) not in (1, 2) or not all(parts):
        raise ValueError(
            f"Invalid table name: {table_name!r}. "
            "Use table_name or schema.table_name."
        )

    # Restrict names to ordinary PostgreSQL identifiers.
    # Quoted or unusual identifiers can be added if needed.
    identifier_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

    for part in parts:
        if not identifier_pattern.fullmatch(part):
            raise ValueError(
                f"Unsupported identifier {part!r}. "
                "Use standard PostgreSQL table and schema names."
            )

    if len(parts) == 1:
        return DEFAULT_SCHEMA, parts[0]

    return parts[0], parts[1]


def export_table(connection, table_name, output_dir):
    schema_name, raw_table_name = parse_table_name(table_name)

    # Resolve exact table name and columns from information schema
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND (table_name = %s OR lower(table_name) = lower(%s))
            LIMIT 1
            """,
            (schema_name, raw_table_name, raw_table_name),
        )
        matched_table = cur.fetchone()
        actual_table_name = matched_table[0] if matched_table else raw_table_name

        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, actual_table_name),
        )
        columns_info = cur.fetchall()

    if columns_info:
        select_exprs = []
        for col_name, data_type in columns_info:
            col_ident = sql.Identifier(col_name)
            # Format booleans explicitly as TRUE / FALSE (preserving NULLs as blank)
            # to prevent PostgreSQL's default 't' / 'f' serialization.
            if data_type == "boolean":
                select_exprs.append(
                    sql.SQL(
                        "CASE WHEN {c} IS TRUE THEN 'TRUE' "
                        "WHEN {c} IS FALSE THEN 'FALSE' "
                        "ELSE NULL END AS {c}"
                    ).format(c=col_ident)
                )
            else:
                select_exprs.append(col_ident)
        select_clause = sql.SQL(", ").join(select_exprs)
    else:
        select_clause = sql.SQL("*")

    # Safely quote SQL identifiers; use NULL '' so null/blank values remain blank in CSV
    query = sql.SQL(
        "COPY (SELECT {} FROM {}.{}) TO STDOUT "
        "WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8', NULL '')"
    ).format(
        select_clause,
        sql.Identifier(schema_name),
        sql.Identifier(actual_table_name),
    )

    # Use the supplied table name for the output filename.
    # Schema-qualified names become schema_table.csv.
    filename = table_name.replace(".", "_") + ".csv"
    output_file = output_dir / filename

    with output_file.open("wb") as csv_file:
        with connection.cursor().copy(query) as copy:
            while True:
                data = copy.read()
                if not data:
                    break
                csv_file.write(data)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Export PostgreSQL tables to CSV files and compress them into a ZIP archive."
    )
    parser.add_argument(
        "tables",
        nargs="*",
        help="Table names, optionally schema-qualified (can also be specified via --tables or TABLES in .env).",
    )
    parser.add_argument(
        "-t",
        "--tables",
        dest="flag_tables",
        nargs="+",
        help="List of table names, optionally schema-qualified.",
    )
    parser.add_argument(
        "-z",
        "--zip-name",
        "--zip-folder",
        dest="zip_name",
        help="Name of the output zip file / folder (e.g. 'my_export' or 'my_export.zip'). Can also be set via ZIP_NAME in .env.",
    )
    args = parser.parse_args()

    output_dir = get_output_dir()

    # Combine positional tables and -t/--tables flag if provided
    cli_tables = (args.tables or []) + (args.flag_tables or [])
    env_tables_str = os.getenv("TABLES") or os.getenv("EXPORT_TABLES")
    tables = resolve_tables(cli_tables, env_tables_str)

    env_zip_name = os.getenv("ZIP_NAME") or os.getenv("ZIP_FOLDER_NAME")
    zip_filename = resolve_zip_name(args.zip_name, env_zip_name)
    zip_stem = Path(zip_filename).stem

    logger, log_file_path = setup_logger(zip_stem)

    if not tables:
        logger.error(
            "No tables specified. Provide tables via command line arguments, "
            "set TABLES in .env, or provide them when prompted."
        )
        sys.exit(1)

    connection_settings = {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "dbname": os.getenv("PG_DB_NAME"),
        "user": os.getenv("PG_USER"),
        "password": os.getenv("PG_PASSWORD"),
        "connect_timeout": 10,
    }

    missing = [
        key for key in ("dbname", "user", "password")
        if not connection_settings[key]
    ]
    if missing:
        logger.error(
            "Missing database settings in .env: "
            + ", ".join(missing)
        )
        sys.exit(1)

    successful = []
    failed = []
    successful_files = []

    try:
        with psycopg.connect(**connection_settings) as connection:
            logger.info(f"Output folder: {output_dir}")
            logger.info(f"Target tables: {', '.join(tables)}")

            for table_name in tables:
                try:
                    output_file = export_table(connection, table_name, output_dir)
                    successful.append(table_name)
                    successful_files.append(output_file)
                    logger.info(f"[SUCCESS] {table_name} -> {output_file.name}")

                except (psycopg.Error, OSError, ValueError) as exc:
                    failed.append(table_name)
                    logger.error(f"[FAILED]  {table_name}: {exc}")

    except psycopg.Error as exc:
        logger.error(f"Database connection failed: {exc}")
        sys.exit(1)

    # Create zip archive of all successfully exported files
    zip_path = None
    if successful_files:
        try:
            zip_path = create_zip_archive(output_dir, zip_filename, successful_files)
            logger.info(f"[ZIP CREATED] {zip_path.name} (contains {len(successful_files)} file(s))")
        except OSError as exc:
            logger.error(f"[ZIP FAILED] Failed to create zip archive: {exc}")
    else:
        logger.warning("No files were exported; skipping zip creation.")

    logger.info("=" * 45)
    logger.info(f"Exported successfully: {len(successful)}")
    logger.info(f"Failed:                {len(failed)}")
    logger.info(f"Output directory:      {output_dir}")
    if zip_path:
        logger.info(f"Zip archive:           {zip_path}")
    logger.info(f"Log file:              {log_file_path}")

    if failed:
        logger.error("Failed tables: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()