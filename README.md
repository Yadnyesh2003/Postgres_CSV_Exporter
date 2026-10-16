# Postgres CSV Exporter

A robust, high-performance PostgreSQL table export utility built with Python and `psycopg 3`. It streams PostgreSQL tables directly into CSV files with zero data manipulation, packages exports into ZIP archives, and supports configuration through CLI arguments, `.env` files, or interactive terminal prompts.

---

## Key Features

- **High-Performance Streaming Export**: Leverages PostgreSQL's native `COPY ... TO STDOUT` mechanism for high-throughput, low-memory CSV generation.
- **Strict Data Fidelity**:
  - **Standard Boolean Formatting**: Exports boolean columns as standard `TRUE` / `FALSE` rather than PostgreSQL's raw `t` / `f` text representations.
  - **True Blank / NULL Preservation**: Empty and `NULL` database values remain cleanly blank in the CSV (`,,`) without unintended placeholders or `\N`.
- **Automatic ZIP Archiving**: Automatically compresses all exported CSV files into a single `.zip` archive while retaining the individual CSV files.
- **Flexible Table Selection**:
  - Command-line arguments: Positional or via `-t` / `--tables`.
  - Environment variable: Define `TABLES` in `.env`.
  - Interactive prompt: Prompts you at runtime if no tables are specified.
- **Customizable ZIP Filename**:
  - Pass via CLI flag (`-z`, `--zip-name`).
  - Configure via `ZIP_NAME` in `.env`.
  - Interactive prompt at runtime with an automatic timestamp fallback (`export_YYYYMMDD_HHMMSS.zip`).
- **Resilient Identifier Matching**:
  - Supports schema-qualified tables (`schema.table_name` or `table_name` using default schema).
  - Performs case-insensitive matching against PostgreSQL system catalogs for mixed-case table identifiers (e.g., `"Projection_Order_Details"`).
- **Dual Console & File Logging**: Automatically writes execution logs to both the terminal and persistent log files under `logs/` formatted as `<ZipName>_<DateTime>.logs`.

---

## Project Structure

```text
Postgres_CSV_Exporter/
├── export_tables.py     # Main export script
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
├── .env                 # Local configuration & credentials (git-ignored)
├── .gitignore           # Git ignore configuration
├── output/              # Exported CSVs and ZIP archives (auto-created)
└── logs/                # Timestamped run logs (auto-created)
```

---

## Requirements

- Python 3.9+
- PostgreSQL database access

---

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/Postgres_CSV_Exporter.git
   cd Postgres_CSV_Exporter
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows PowerShell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy `.env.example` to `.env` and fill in your PostgreSQL credentials:
   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   ```env
   PG_HOST = localhost
   PG_PORT = 5432
   PG_DB_NAME = your_database_name
   PG_USER = postgres
   PG_PASSWORD = your_password

   # Optional configurations
   OUTPUT_DIR = output
   PG_SCHEMA = public
   TABLES = 
   ZIP_NAME = 
   ```

---

## Configuration Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `PG_HOST` | Yes | `localhost` | PostgreSQL host address |
| `PG_PORT` | Yes | `5432` | PostgreSQL port |
| `PG_DB_NAME` | Yes | — | Database name |
| `PG_USER` | Yes | — | Database user |
| `PG_PASSWORD` | Yes | — | Database password |
| `PG_SCHEMA` | No | `public` | Default PostgreSQL schema |
| `OUTPUT_DIR` | No | `output` | Target folder for CSVs and ZIP archives |
| `TABLES` | No | — | Comma- or space-separated default tables |
| `ZIP_NAME` | No | Timestamped | Default name for output ZIP archive |

---

## Usage

### 1. Using Command-Line Arguments (Recommended)

Specify table names and an optional zip name directly:
```bash
python export_tables.py table1 table2 -z my_bundle
```

Using the `-t` / `--tables` flag:
```bash
python export_tables.py -t Allocation_Sequence,Batchwise_OrderAllocation -z monthly_backup
```

Schema-qualified tables:
```bash
python export_tables.py public.Projection_Order custom_schema.Order_Details -z inventory_run
```

### 2. Using `.env` Configuration

Define the tables and zip name in `.env`:
```env
TABLES = Allocation_Sequence, Batchwise_OrderAllocation, Projection_Order
ZIP_NAME = daily_export
```

Then simply execute:
```bash
python export_tables.py
```

### 3. Interactive Mode

Run the script without arguments or `.env` table settings:
```bash
python export_tables.py
```
You will be prompted:
```text
Enter table name(s) to export (separated by comma or space): Projection_Order_Details
Enter zip file/folder name (press Enter for timestamped default): run_october
```

---

## Command-Line Options

```text
usage: export_tables.py [-h] [-t FLAG_TABLES [FLAG_TABLES ...]] [-z ZIP_NAME] [tables ...]

Export PostgreSQL tables to CSV files and compress them into a ZIP archive.

positional arguments:
  tables                Table names, optionally schema-qualified.

options:
  -h, --help            Show this help message and exit.
  -t, --tables          List of table names, optionally schema-qualified.
  -z, --zip-name, --zip-folder
                        Name of the output zip file / folder.
```

---

## Output & Logs

- **Exported CSV Files**: Stored in `output/` (or your configured `OUTPUT_DIR`).
- **ZIP Archive**: Created in `output/<zip_name>.zip` containing all exported CSVs from the run.
- **Log Files**: Stored in `logs/<zip_name>_<YYYYMMDD_HHMMSS>.logs` with execution details and error reporting.

Example Log Output:
```text
2026-10-16 11:23:43 [INFO] Output folder: D:\Postgres_CSV_Exporter\output
2026-10-16 11:23:43 [INFO] Target tables: Projection_Order_Details
2026-10-16 11:23:43 [INFO] [SUCCESS] Projection_Order_Details -> Projection_Order_Details.csv
2026-10-16 11:23:43 [INFO] [ZIP CREATED] run_october.zip (contains 1 file(s))
2026-10-16 11:23:43 [INFO] =============================================
2026-10-16 11:23:43 [INFO] Exported successfully: 1
2026-10-16 11:23:43 [INFO] Failed:                0
2026-10-16 11:23:43 [INFO] Output directory:      D:\Postgres_CSV_Exporter\output
2026-10-16 11:23:43 [INFO] Zip archive:           D:\Postgres_CSV_Exporter\output\run_october.zip
2026-10-16 11:23:43 [INFO] Log file:              D:\Postgres_CSV_Exporter\logs\run_october_20261016_112343.logs
```

---

## License

MIT License. Free for personal and commercial use.
