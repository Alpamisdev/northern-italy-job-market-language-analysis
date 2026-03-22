import sqlite3
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# Fix algorithm seed for deterministic results
DetectorFactory.seed = 0

def impute_missing_languages(db_path='glassdoor_jobs.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Extract only the blind spot (unclassified vacancies)
    cursor.execute('''
        SELECT id, description 
        FROM jobs 
        WHERE english_status = 'Not Mentioned' 
          AND italian_status = 'Not Mentioned'
          AND description IS NOT NULL
    ''')
    jobs = cursor.fetchall()
    
    if not jobs:
        print("[!] No blind spots found. Database is clean.")
        return

    data_to_update = []
    en_count, it_count = 0
    
    for job_id, description in jobs:
        try:
            # Detect description language
            lang = detect(description)
        except LangDetectException:
            continue # Skip corrupted strings or unidentifiable languages
            
        # Apply business logic: infer language requirement from description language
        if lang == 'en':
            en_status, en_lvl = 'Mandatory (Imputed)', 'B2'
            it_status, it_lvl = 'Not Required (Imputed)', None
            en_count += 1
        elif lang == 'it':
            en_status, en_lvl = 'Not Required (Imputed)', None
            it_status, it_lvl = 'Mandatory (Imputed)', 'C1'
            it_count += 1
        else:
            continue # Ignore other languages (e.g., German in Trentino)
            
        data_to_update.append((en_status, en_lvl, it_status, it_lvl, job_id))
        
    # Batch update database
    cursor.executemany('''
        UPDATE jobs 
        SET english_status = ?, english_level = ?,
            italian_status = ?, italian_level = ?
        WHERE id = ?
    ''', data_to_update)
    
    conn.commit()
    conn.close()
    
    print(f"[+] Imputation completed.")
    print(f"[>] English vacancies imputed: {en_count}")
    print(f"[>] Italian vacancies imputed: {it_count}")

if __name__ == '__main__':
    impute_missing_languages()