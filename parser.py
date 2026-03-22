import time
import random
import sqlite3
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    ElementClickInterceptedException, 
    TimeoutException, 
    NoSuchElementException,
    StaleElementReferenceException
)

# ==========================================
# 1. DATABASE BLOCK
# ==========================================
def setup_database():
    """Initializes relational DB. Creates 3NF structure without salary columns."""
    try:
        conn = sqlite3.connect('glassdoor_jobs.db')
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            glassdoor_id TEXT UNIQUE NOT NULL,
            company_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            link TEXT NOT NULL,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies (id),
            FOREIGN KEY (location_id) REFERENCES locations (id)
        )''')
        conn.commit()
        return conn, cursor
    except Exception as e:
        print(f"[CRITICAL DB ERROR] Failed to initialize database: {e}")
        exit(1)

def get_or_create_id(cursor, table, name):
    """Ensures unique records in lookup tables (companies, locations)."""
    try:
        cursor.execute(f"INSERT OR IGNORE INTO {table} (name) VALUES (?)", (name,))
        cursor.execute(f"SELECT id FROM {table} WHERE name = ?", (name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"[DB ERROR] Error operating on table {table}: {e}")
        return None

# ==========================================
# 2. DATA PROCESSING BLOCK
# ==========================================
def extract_job_id(link):
    """Extracts unique 13-digit job ID from URL to prevent duplicates."""
    try:
        return link.split('jl=')[-1].split('&')[0]
    except Exception:
        return str(random.randint(1000000, 9999999))

# ==========================================
# 3. BROWSER CONTROL BLOCK
# ==========================================
def close_popups(driver):
    """Aggressively destroys any popups blocking the screen."""
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        selectors = ['button.CloseButton', '[data-test="ModalClose"]', '.modal_closeIcon']
        for sel in selectors:
            for btn in driver.find_elements(By.CSS_SELECTOR, sel):
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.3)
    except Exception:
        pass

def scrape_active_glassdoor_tab():
    """Main scraping loop via Remote Debugging."""
    db_conn, db_cursor = setup_database()

    try:
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 10)
        print("[i] Successfully connected to browser on port 9222.")
    except Exception as e:
        print(f"[CRITICAL ERROR] Failed to connect to Chrome. Is it running with --remote-debugging-port=9222? Error: {e}")
        return

    processed_ids = set()
    total_saved = 0
    iteration = 1
    
    try:
        while True:
            print(f"\n[*] Processing list. Iteration {iteration}...")
            
            card_selector = 'li[data-test="jobListing"]'
            try:
                wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, card_selector)))
            except TimeoutException:
                print("[-] Job cards not found on page. Check the browser tab.")
                break

            time.sleep(2)
            close_popups(driver)
            
            # Lock element count. Process by index to avoid StaleElementReferenceException
            cards_count = len(driver.find_elements(By.CSS_SELECTOR, card_selector))
            print(f"[i] Cards in left column: {cards_count}")
            new_cards = 0
            
            for index in range(cards_count):
                try:
                    # Dynamically capture card by index
                    cards = driver.find_elements(By.CSS_SELECTOR, card_selector)
                    if index >= len(cards):
                        break
                    card = cards[index]
                    
                    # Extract basic data
                    title_elem = card.find_element(By.CSS_SELECTOR, 'a[data-test="job-title"]')
                    title = title_elem.text.strip()
                    link = title_elem.get_attribute('href')
                    
                    job_id = extract_job_id(link)
                    
                    # Check for duplicates in memory
                    if job_id in processed_ids:
                        continue
                    
                    # Check for duplicates in DB (protection during script restarts)
                    db_cursor.execute("SELECT 1 FROM jobs WHERE glassdoor_id = ?", (job_id,))
                    if db_cursor.fetchone():
                        processed_ids.add(job_id)
                        continue

                    # Extract company
                    try:
                        company = card.find_element(By.CSS_SELECTOR, 'span[class*="EmployerProfile_compactEmployerName"]').text.strip()
                    except NoSuchElementException:
                        company = "Not specified"
                        
                    # Extract location
                    try:
                        location = card.find_element(By.CSS_SELECTOR, '[data-test="emp-location"]').text.strip()
                    except NoSuchElementException:
                        location = "Not specified"

                    # Scroll to card and click to load right panel
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                    time.sleep(random.uniform(0.3, 0.6))
                    
                    try:
                        card.click()
                    except (ElementClickInterceptedException, StaleElementReferenceException):
                        close_popups(driver)
                        driver.execute_script("arguments[0].click();", card)

                    # Wait for right panel to load job details
                    right_panel_h1 = 'div[class*="JobDetails_jobDetailsContainer"] h1'
                    try:
                        wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, right_panel_h1), title))
                    except TimeoutException:
                        print(f"    [!] Right panel did not update for: {title}. Skipping.")
                        continue
                    
                    time.sleep(0.5) 
                    
                    # Expand full description (Show More button inside right panel)
                    try:
                        inner_show_more = driver.find_element(By.CSS_SELECTOR, 'button[data-test="show-more-cta"]')
                        if inner_show_more.is_displayed():
                            driver.execute_script("arguments[0].click();", inner_show_more)
                            time.sleep(0.5)
                    except NoSuchElementException:
                        pass # No button, description is fully open
                    
                    # Extract full description
                    try:
                        desc_selector = 'div[class*="JobDetails_jobDescription"]'
                        desc_elem = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, desc_selector)))
                        full_description = desc_elem.text.strip()
                    except TimeoutException:
                        full_description = "Description parsing failed"

                    # Write to DB
                    c_id = get_or_create_id(db_cursor, 'companies', company)
                    l_id = get_or_create_id(db_cursor, 'locations', location)
                    
                    if c_id is None or l_id is None:
                        raise Exception("Foreign Key (Company/Location) creation failed.")
                    
                    db_cursor.execute('''
                        INSERT OR IGNORE INTO jobs 
                        (glassdoor_id, company_id, location_id, title, description, link)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (job_id, c_id, l_id, title, full_description, link))
                    
                    db_conn.commit() # Hard commit transaction after each job
                    
                    processed_ids.add(job_id)
                    new_cards += 1
                    total_saved += 1
                    
                    print(f"    [+] {company} | {title} saved.")
                    
                except Exception as e:
                    # Catch any error on specific card so script moves to next
                    print(f"    [-] Critical failure on card {index}: {type(e).__name__}")
                    # traceback.print_exc() # Uncomment for deep debugging
                    continue
            
            if new_cards == 0:
                print("[i] No new jobs found in this block.")
                
            # Move to next block of cards (pagination at bottom of list)
            try:
                close_popups(driver)
                # Re-fetch current cards before scrolling
                current_cards = driver.find_elements(By.CSS_SELECTOR, card_selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", current_cards[-1])
                time.sleep(1.5)
                
                xpath_selector = '//div[contains(@class, "JobsList_wrapper")]//button[not(ancestor::li)]'
                bottom_buttons = driver.find_elements(By.XPATH, xpath_selector)
                
                show_more_btn = next((btn for btn in bottom_buttons if btn.is_displayed() and len(btn.text.strip()) > 0), None)
                
                if show_more_btn and show_more_btn.is_enabled():
                    driver.execute_script("arguments[0].scrollIntoView(false); window.scrollBy(0, 200);", show_more_btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", show_more_btn)
                    
                    print("\n[i] 'Show more' button clicked. Waiting for load...")
                    # Wait for card count to exceed previous count
                    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, card_selector)) > cards_count)
                    time.sleep(2)
                    iteration += 1
                else:
                    print("\n[i] 'Show more' button hidden or disabled. End of results.")
                    break
                    
            except TimeoutException:
                print("\n[-] New cards did not load after click. Possible end of results.")
                break
            except Exception as e:
                print(f"\n[-] Error finding pagination button: {type(e).__name__}")
                break

    except KeyboardInterrupt:
        print("\n[!] Script stopped by user (Ctrl+C).")
    finally:
        try:
            db_conn.close()
            print(f"\n[+] Total new jobs saved: {total_saved}. Database disconnected.")
        except Exception:
            pass

if __name__ == '__main__':
    scrape_active_glassdoor_tab()