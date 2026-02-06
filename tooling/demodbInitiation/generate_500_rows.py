#!/usr/bin/env python3
"""Generate 500 rows of dummy data and load into PostgreSQL database."""

import csv
import json
import random
import string
import sys
from pathlib import Path

# Add parent directory to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load schema
schema_path = PROJECT_ROOT / 'data' / 'schema_data.json'
with open(schema_path, 'r') as f:
    schema = json.load(f)

# Extract field names
fields = [field['name'] for field in schema['fields']]

def generate_dummy_row():
    """Generate a single row of dummy data."""
    row = {}
    for field in schema['fields']:
        name = field['name']
        field_type = field['type']
        
        if 'String' in field_type:
            if name == 'PatientID':
                row[name] = f"PAT{random.randint(1000, 9999)}"
            elif name == 'Variant_key':
                row[name] = f"VAR_{random.randint(10000, 99999)}"
            elif name == 'Wt_nmer':
                row[name] = ''.join(random.choices('ACGT', k=9))
            elif name == 'Mut_nmer':
                row[name] = ''.join(random.choices('ACGT', k=9))
            elif name == 'Gene_names':
                genes = ['TP53', 'EGFR', 'BRCA1', 'KRAS', 'MYC', 'PTEN', 'APC', 'RB1']
                row[name] = random.choice(genes)
            elif name == 'Exonic_Functions':
                funcs = ['nonsynonymous SNV', 'frameshift deletion', 'frameshift insertion', 'stopgain']
                row[name] = random.choice(funcs)
            elif name == 'Status':
                row[name] = random.choice(['Active', 'Inactive', 'Pending', 'Reviewed'])
            elif name == 'Screened':
                row[name] = random.choice(['Yes', 'No'])
            elif 'annotation' in name or 'transcript' in name or 'exons' in name or 'cDNA' in name or 'aa_changes' in name:
                row[name] = f"ANNOT_{random.randint(1000, 9999)}"
            elif 'TMG' in name:
                row[name] = random.choice(['Y', 'N', ''])
            elif 'Epitope' in name:
                row[name] = f"EPI_{random.randint(100, 999)}"
            else:
                row[name] = ''.join(random.choices(string.ascii_letters, k=10))
                
        elif 'Double' in field_type:
            row[name] = round(random.uniform(0, 100), 4)
            
        elif 'Long' in field_type:
            row[name] = random.randint(0, 100)
    
    return row

def main():
    from sqlalchemy import create_engine, text
    
    # Generate 500 unique rows (unique by PatientID_Mutsequence)
    print("Generating 500 rows of dummy data...")
    
    seen_pks = set()
    dummy_data = []
    
    while len(dummy_data) < 500:
        row = generate_dummy_row()
        # PatientID_Mutsequence is a column in the data that serves as the PK
        pk = row.get('PatientID_Mutsequence')
        if pk not in seen_pks:
            seen_pks.add(pk)
            dummy_data.append(row)
    
    print(f"Generated {len(dummy_data)} unique rows")
    
    # Connect to database
    connection_string = "postgresql://her2@localhost/epitopes_db"
    engine = create_engine(connection_string)
    
    with engine.connect() as conn:
        # Clear existing data
        print("Clearing existing data...")
        conn.execute(text("DELETE FROM epitopes_modifications"))
        conn.execute(text("DELETE FROM epitopes_ui_state"))
        conn.execute(text("DELETE FROM epitopes_data"))
        conn.commit()
        
        # Drop old primary key constraint if exists
        try:
            conn.execute(text("ALTER TABLE epitopes_data DROP CONSTRAINT IF EXISTS epitopes_data_pkey"))
            conn.commit()
        except:
            pass
        
        # Insert new data
        print("Inserting 500 rows into database...")
        
        # Build insert statement
        columns = list(dummy_data[0].keys())
        placeholders = ', '.join([f':{col}' for col in columns])
        columns_str = ', '.join([f'"{col}"' for col in columns])
        
        insert_sql = text(f'INSERT INTO epitopes_data ({columns_str}) VALUES ({placeholders})')
        
        for row in dummy_data:
            conn.execute(insert_sql, row)
        
        conn.commit()
        
        # Add new primary key constraint on PatientID_Mutsequence
        print("Adding primary key constraint on PatientID_Mutsequence...")
        conn.execute(text('ALTER TABLE epitopes_data ADD PRIMARY KEY ("PatientID_Mutsequence")'))
        conn.commit()
        
        # Verify
        result = conn.execute(text("SELECT COUNT(*) FROM epitopes_data"))
        count = result.scalar()
        print(f"✓ Loaded {count} rows into epitopes_data")
        
        # Show sample
        result = conn.execute(text('SELECT "PatientID", "PatientID_Mutsequence" FROM epitopes_data LIMIT 3'))
        print("\nSample rows:")
        for row in result:
            print(f"  PatientID: {row[0]}, PK: {row[1]}")

if __name__ == "__main__":
    main()
