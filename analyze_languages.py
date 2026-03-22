import sqlite3
import re
import time

# ==========================================
# 1. REGEX PRE-COMPILATION (PERFORMANCE)
# ==========================================
# Context window capture: search for the language and grab up to 50 characters around it, 
# strictly within the same sentence (stops at period, semicolon, or newline) to prevent data leakage.
EN_LANG_REGEX = re.compile(r'([^.;\n]{0,50}\b(?:english|inglese)\b[^.;\n]{0,50})', re.IGNORECASE)
IT_LANG_REGEX = re.compile(r'([^.;\n]{0,50}\b(?:italian|italiano|madrelingua)\b[^.;\n]{0,50})', re.IGNORECASE)

# CEFR scale with numeric ranks for the minimum threshold algorithm
CEFR_RANKS = {
    r'\b(a1|basic|base|scolastico|beginner)\b': 1,
    r'\b(a2|pre[- ]intermediate|elementare)\b': 2,
    r'\b(b1|intermediate|intermedio|working knowledge)\b': 3,
    r'\b(b2|upper intermediate|medio[- ]alto|autonomo|good|buon[oa]?|strong)\b': 4,
    r'\b(c1|fluent|fluente|fluency|proficient|proficiency|ottim[oa]?|eccellente|excellent|advanced|avanzat[oa]?)\b': 5,
    r'\b(c2|native|mother tongue|bilingual|bilingue|mastery)\b': 6
}
# Compile level patterns once into memory
COMPILED_CEFR = {re.compile(pattern, re.IGNORECASE): rank for pattern, rank in CEFR_RANKS.items()}
RANK_TO_CEFR = {1: 'A1', 2: 'A2', 3: 'B1', 4: 'B2', 5: 'C1', 6: 'C2'}

# Status triggers
NEGATION_REGEX = re.compile(r'\b(non richiest[oa]|non necessari[oa]|not required|not mandatory|not needed|senza)\b', re.IGNORECASE)
OPTIONAL_REGEX = re.compile(r'\b(nice to have|plus|optional|preferred|advantage|bonus|gradit[oa]|preferibil[e]|preferenzial[e]|vantaggi[o])\b', re.IGNORECASE)
MANDATORY_REGEX = re.compile(r'\b(essential|mandatory|must|richiest[oa]|obbligatori[oa]|fondamentale|indispensabile|fluency in|fluent in)\b', re.IGNORECASE)

# ==========================================
# 2. ISOLATED SEMANTIC ANALYZER
# ==========================================
def extract_language_requirements(text, lang_regex):
    if not text:
        return "Not Mentioned", None
        
    # STEP 1: Context window extraction
    # Slice only text segments where the target language is actually mentioned.
    windows = lang_regex.findall(text)
    if not windows:
        return "Not Mentioned", None
        
    # Combine all found windows into a single string for focused analysis
    combined_context = " || ".join(windows).lower()
    
    # STEP 2: Negation check
    if NEGATION_REGEX.search(combined_context):
        return "Not Required", None
        
    # STEP 3: Level detection (Minimum Threshold Algorithm)
    found_ranks = []
    for regex, rank in COMPILED_CEFR.items():
        if regex.search(combined_context):
            found_ranks.append(rank)
            
    # If multiple levels are found (e.g., "B2 / C1"), extract the minimum (B2) to avoid barrier inflation
    final_level = RANK_TO_CEFR.get(min(found_ranks)) if found_ranks else None
    
    # STEP 4: Status determination (Mandatory vs Optional)
    # By default, the language is mandatory if mentioned and not explicitly negated
    status = "Mandatory" 
    # If 'plus' words exist but NO strict 'mandatory' words are in the same window
    if OPTIONAL_REGEX.search(combined_context) and not MANDATORY_REGEX.search(combined_context):
        status = "Plus (Optional)"
        
    return status, final_level

# ==========================================
# 3. DATABASE AND BATCH PROCESSING
# ==========================================
def run_analysis(db_path='glassdoor_jobs.db'):
    start_time = time.time()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Dynamically create columns if they don't exist
    for col in ["english_status", "english_level", "italian_status", "italian_level"]:
        try:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
            
    cursor.execute("SELECT id, description FROM jobs WHERE description IS NOT NULL")
    jobs = cursor.fetchall()
    
    total_jobs = len(jobs)
    print(f"[*] Target DB: {db_path}")
    print(f"[*] Vacancies found for analysis: {total_jobs}")
    
    if total_jobs == 0:
        print("[!] Warning: Nothing to analyze. Check the DB file path.")
        return

    data_to_update = []
    for job_id, description in jobs:
        en_status, en_level = extract_language_requirements(description, EN_LANG_REGEX)
        it_status, it_level = extract_language_requirements(description, IT_LANG_REGEX)
        data_to_update.append((en_status, en_level, it_status, it_level, job_id))
        
    # Batch update for performance
    cursor.executemany('''
        UPDATE jobs 
        SET english_status = ?, english_level = ?,
            italian_status = ?, italian_level = ?
        WHERE id = ?
    ''', data_to_update)
    
    conn.commit()
    conn.close()
    
    elapsed = time.time() - start_time
    print(f"[+] Successfully updated {total_jobs} records in {elapsed:.2f} seconds.")

if __name__ == '__main__':
    run_analysis()