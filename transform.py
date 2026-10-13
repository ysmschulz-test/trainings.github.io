import csv
import json
import re
from datetime import datetime
from pathlib import Path


# ==========================================
# HELPER: Date Standardization Engine
# ==========================================
def standardize_date(date_str):
    """
    Converts various Czech and standard string date formats (e.g., '10. 7. 2027',
    '2027-05-22', '10.07.2027') securely into standardized 'YYYY-MM-DD' strings.
    """
    if not date_str or not date_str.strip():
        return None

    date_clean = date_str.strip()

    # Format Try 1: ISO Format (YYYY-MM-DD)
    try:
        return datetime.strptime(date_clean, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    # Format Try 2: Czech format with spaces/dots (D. M. YYYY or DD.MM.YYYY)
    # Cleans "10. 7. 2027" -> "10.7.2027"
    normalized_cz = re.sub(r'\s+', '', date_clean)

    # Try various Czech text patterns
    for pattern in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(normalized_cz, pattern).date().isoformat()
        except ValueError:
            pass

    # Return original string safe fallback if parsing fails entirely
    return date_clean


# ==========================================
# PART 1: Process Employee Data
# ==========================================
csv_file_path = 'input/zamestnanci.csv'
utvar_json_path = Path('data/utvar.json')
pozice_json_path = Path('data/pozice.json')
zamestnanci_json_path = Path('data/zamestnanci.json')

for json_path in [utvar_json_path, pozice_json_path, zamestnanci_json_path]:
    if json_path.exists():
        json_path.unlink()
    json_path.touch()

utvar_map = {}
pozice_map = {}
zamestnanci_list = []

with open(csv_file_path, mode='r', encoding='utf-8-sig') as csv_file:
    reader = csv.DictReader(csv_file)
    utvar_counter = 1
    pozice_counter = 1

    for row in reader:
        utvar_name = row['utvar'].strip()
        if utvar_name and utvar_name not in utvar_map:
            utvar_map[utvar_name] = utvar_counter
            utvar_counter += 1

        pozice_name = row['pozice'].strip()
        if pozice_name and pozice_name not in pozice_map:
            pozice_map[pozice_name] = pozice_counter
            pozice_counter += 1

        row['utvar'] = utvar_map.get(utvar_name)
        row['pozice'] = pozice_map.get(pozice_name)
        zamestnanci_list.append(row)

utvar_output = [{"id": v, "nazev": k} for k, v in utvar_map.items()]
pozice_output = [{"id": v, "nazev": k} for k, v in pozice_map.items()]

with open(utvar_json_path, mode='w', encoding='utf-8') as f:
    json.dump(utvar_output, f, ensure_ascii=False, indent=4)
with open(pozice_json_path, mode='w', encoding='utf-8') as f:
    json.dump(pozice_output, f, ensure_ascii=False, indent=4)
with open(zamestnanci_json_path, mode='w', encoding='utf-8') as f:
    json.dump(zamestnanci_list, f, ensure_ascii=False, indent=4)

print("Employee files successfully reset and populated!")

# ==========================================
# PART 2: Load Completed Training Records (with Date Normalization)
# ==========================================
completed_csv_path = 'input/absolvovana_skoleni.csv'
history_map = {}

try:
    with open(completed_csv_path, mode='r', encoding='cp1250') as csv_file:
        reader = csv.DictReader(csv_file, delimiter=';')
        for row in reader:
            k_skoleni = row['kod_skoleni'].strip() if row['kod_skoleni'] else ""
            id_zam = row['id_zamestnance'].strip() if row['id_zamestnance'] else ""
            p_do = row['platnost_do'].strip() if row['platnost_do'] else ""

            key = (k_skoleni, id_zam)
            # Standardize string formats down to YYYY-MM-DD
            history_map[key] = standardize_date(p_do)
except FileNotFoundError:
    print(f"Warning: {completed_csv_path} not found.")
except KeyError as e:
    print(f"Error: Column {e} not found in {completed_csv_path}.")

# ==========================================
# PART 3: Parse Upcoming Schedules & Terms (New Feature)
# ==========================================
schedule_csv_path = 'input/terminy_skoleni.csv'
schedule_map = {}  # Format: { "KOD_SKOLENI": [{"datum": "...", "cas": "..."}, ...] }

try:
    with open(schedule_csv_path, mode='r', encoding='cp1250') as csv_file:
        reader = csv.DictReader(csv_file, delimiter=';')
        for row in reader:
            k_skoleni = row['kod_skoleni'].strip() if row['kod_skoleni'] else ""
            raw_datum = row['datum'].strip() if row['datum'] else ""
            cas_skoleni = row['cas'].strip() if row['cas'] else ""

            if k_skoleni:
                if k_skoleni not in schedule_map:
                    schedule_map[k_skoleni] = []

                # Standardize session calendar date strings
                clean_datum = standardize_date(raw_datum)

                schedule_map[k_skoleni].append({
                    "datum": clean_datum,
                    "cas": cas_skoleni
                })
except FileNotFoundError:
    print(f"Warning: {schedule_csv_path} not found. Proceeding with empty schedules.")

# ==========================================
# PART 4: Process Training Catalog & Build Final JSONs
# ==========================================
katalog_csv_path = 'input/katalog_skoleni.csv'
output_dir = Path('data/skoleni')
kody_json_path = Path('data/kody_skoleni.json')

# Clean and prepare output directory for individual training files
if output_dir.exists():
    for f in output_dir.glob('*.json'):
        f.unlink()
else:
    output_dir.mkdir(parents=True, exist_ok=True)

# In-memory dictionaries to resolve IDs back to strings for rule evaluation
utvary_lookup = {item['id']: item['nazev'] for item in utvar_output}
pozice_lookup = {item['id']: item['nazev'] for item in pozice_output}

kody_skoleni_list = []

# Read training catalog and map employees
with open(katalog_csv_path, mode='r', encoding='utf-8-sig') as csv_file:
    reader = csv.DictReader(csv_file)

    for training in reader:
        training_code = training['kod'].strip()
        rule = training['povinne_pro'].strip()

        if training_code and training_code not in kody_skoleni_list:
            kody_skoleni_list.append(training_code)

        if not rule or rule == 'NEPOVINNE':
            matched_employees = []
        elif rule == 'VSICHNI':
            matched_employees = zamestnanci_list
        elif rule.startswith('UTVAR:'):
            allowed_utvary = [u.strip() for u in rule.replace('UTVAR:', '').split(';')]
            matched_employees = [
                emp for emp in zamestnanci_list
                if utvary_lookup.get(emp['utvar']) in allowed_utvary
            ]
        elif rule.startswith('POZICE:'):
            allowed_pozice = [p.strip() for p in rule.replace('POZICE:', '').split(';')]
            matched_employees = [
                emp for emp in zamestnanci_list
                if pozice_lookup.get(emp['pozice']) in allowed_pozice
            ]
        else:
            matched_employees = []

        final_assigned_employees = []
        for emp in matched_employees:
            emp_copy = emp.copy()
            lookup_key = (training_code, str(emp_copy['id_zamestnance']))
            emp_copy['platnost_do'] = history_map.get(lookup_key, None)
            final_assigned_employees.append(emp_copy)

        # Fetch terms list allocated to this current course code (defaults to empty list if none)
        assigned_terms = schedule_map.get(training_code, [])

        # Construct final enriched schema design
        output_data = {
            "training_info": {
                "kod": training_code,
                "nazev": training['nazev'].strip(),
                "platnost_mesicu": training['platnost_mesicu'].strip(),
                "povinne_pro": rule,
                "poznamka": training['poznamka'].strip(),
                "terminy": assigned_terms  # Array injection added here
            },
            "employees": final_assigned_employees
        }

        safe_filename = re.sub(r'[\\/*?:"<>|]', "", training_code) + '.json'
        with open(output_dir / safe_filename, 'w', encoding='utf-8') as out_f:
            json.dump(output_data, out_f, ensure_ascii=False, indent=4)

if kody_json_path.exists():
    kody_json_path.unlink()

with open(kody_json_path, mode='w', encoding='utf-8') as f:
    json.dump(kody_skoleni_list, f, ensure_ascii=False, indent=4)

print(f"Enriched training files successfully created in '{output_dir}' folder!")