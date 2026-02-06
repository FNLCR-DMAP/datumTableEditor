#!/usr/bin/env python3
"""
Initialize PostgreSQL database with epitopes data.

Creates tables and loads data from CSV.
"""

import pandas as pd
from pathlib import Path

try:
    from sqlalchemy import create_engine, text
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    print("SQLAlchemy not installed. Run: pip install sqlalchemy psycopg2-binary")
    exit(1)


# Database configuration
DB_CONNECTION = "postgresql://her2@localhost/epitopes_db"
DATA_TABLE = "epitopes_data"
MODS_TABLE = "epitopes_modifications"
STATE_TABLE = "epitopes_ui_state"

# Project root and CSV file path
PROJECT_ROOT = Path(__file__).parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "dummy_data_50rows.csv"


def create_tables(engine):
    """Create the modifications and state tables."""
    
    with engine.connect() as conn:
        # Create modifications table
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{MODS_TABLE}" (
                id SERIAL PRIMARY KEY,
                row_pk JSONB NOT NULL,
                column_name VARCHAR(255) NOT NULL,
                old_value TEXT,
                new_value TEXT,
                mod_type VARCHAR(50) NOT NULL DEFAULT 'field_modification',
                created_by VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                undone BOOLEAN DEFAULT FALSE
            )
        """))
        
        # Create index on row_pk for faster lookups
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{MODS_TABLE}_row_pk 
            ON "{MODS_TABLE}" USING GIN (row_pk)
        """))
        
        # Create state table
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{STATE_TABLE}" (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                session_id VARCHAR(255) NOT NULL,
                filters JSONB,
                sort_column VARCHAR(255),
                sort_ascending BOOLEAN DEFAULT TRUE,
                current_page INTEGER DEFAULT 1,
                rows_per_page INTEGER DEFAULT 25,
                column_preset VARCHAR(255),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, session_id)
            )
        """))
        
        conn.commit()
        print(f"✓ Created tables: {MODS_TABLE}, {STATE_TABLE}")


def load_csv_to_db(engine, csv_path: Path):
    """Load CSV data into the database."""
    
    if not csv_path.exists():
        print(f"✗ CSV file not found: {csv_path}")
        return False
    
    # Read CSV
    df = pd.read_csv(csv_path)
    print(f"✓ Read {len(df)} rows from {csv_path.name}")
    
    # Load to database (replace if exists)
    df.to_sql(DATA_TABLE, engine, if_exists='replace', index=False)
    print(f"✓ Loaded data into table: {DATA_TABLE}")
    
    # Add primary key constraint
    with engine.connect() as conn:
        # Check if PK exists
        result = conn.execute(text(f"""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = '{DATA_TABLE}' AND constraint_type = 'PRIMARY KEY'
        """))
        
        if result.fetchone() is None:
            # Add composite primary key
            conn.execute(text(f"""
                ALTER TABLE "{DATA_TABLE}" 
                ADD PRIMARY KEY ("PatientID", "Variant_key")
            """))
            conn.commit()
            print(f"✓ Added primary key: (PatientID, Variant_key)")
    
    return True


def verify_setup(engine):
    """Verify the database setup."""
    
    with engine.connect() as conn:
        # Check data table
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{DATA_TABLE}"'))
        count = result.scalar()
        print(f"\n✓ Data table '{DATA_TABLE}': {count} rows")
        
        # Check column names
        result = conn.execute(text(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = '{DATA_TABLE}' LIMIT 10
        """))
        cols = [row[0] for row in result.fetchall()]
        print(f"  Columns (first 10): {', '.join(cols)}")
        
        # Check mods table
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{MODS_TABLE}"'))
        count = result.scalar()
        print(f"✓ Mods table '{MODS_TABLE}': {count} rows")
        
        # Check state table
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{STATE_TABLE}"'))
        count = result.scalar()
        print(f"✓ State table '{STATE_TABLE}': {count} rows")


def main():
    print("=" * 60)
    print("Epitopes Database Initialization")
    print("=" * 60)
    print(f"\nConnection: {DB_CONNECTION}")
    print(f"Data file:  {CSV_PATH}\n")
    
    # Create engine
    engine = create_engine(DB_CONNECTION)
    
    # Test connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Connected to database\n")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return
    
    # Create supporting tables
    create_tables(engine)
    
    # Load CSV data
    load_csv_to_db(engine, CSV_PATH)
    
    # Verify
    verify_setup(engine)
    
    print("\n" + "=" * 60)
    print("Database initialization complete!")
    print("=" * 60)
    print(f"\nUpdate app_config.json to use database mode:")
    print(f'  "database": {{"enabled": true, ...}}')


if __name__ == "__main__":
    main()
