import csv
import json
import random
from datetime import datetime
import string

# Load schema
with open('schema_data.json', 'r') as f:
    schema = json.load(f)

# Extract field names
fields = [field['name'] for field in schema['fields']]

# Generate dummy data
def generate_dummy_row():
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
                row[name] = random.choice(['Y', 'N', None])
            elif 'Epitope' in name:
                row[name] = f"EPI_{random.randint(100, 999)}"
            else:
                row[name] = ''.join(random.choices(string.ascii_letters, k=10))
                
        elif 'Double' in field_type:
            row[name] = round(random.uniform(0, 100), 4)
            
        elif 'Long' in field_type:
            row[name] = random.randint(0, 100)
    
    return row

# Generate 50 rows
dummy_data = [generate_dummy_row() for _ in range(50)]

# Write to CSV
output_file = 'dummy_data_50rows.csv'
with open(output_file, 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fields)
    writer.writeheader()
    writer.writerows(dummy_data)

print(f"Generated {len(dummy_data)} rows of dummy data")
print(f"Saved to {output_file}")
print(f"Fields: {len(fields)}")
