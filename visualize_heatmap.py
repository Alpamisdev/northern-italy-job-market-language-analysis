import sqlite3
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

def generate_heatmap(db_path='glassdoor_jobs.db'):
    conn = sqlite3.connect(db_path)
    
    # Extract data, replacing NULL with 'Not Spec' for brevity on the chart
    query = """
    SELECT 
        COALESCE(english_level, 'Not Spec') AS English,
        COALESCE(italian_level, 'Not Spec') AS Italian,
        COUNT(*) AS Vacancies
    FROM jobs
    GROUP BY English, Italian
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Pivot table for Seaborn
    pivot_table = df.pivot(index="Italian", columns="English", values="Vacancies").fillna(0)
    
    # Strictly define CEFR axis order (weakest to strongest)
    order = ['Not Spec', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    
    # Keep only columns/rows actually present in the data
    valid_cols = [col for col in order if col in pivot_table.columns]
    valid_rows = [row for row in order if row in pivot_table.index]
    pivot_table = pivot_table.loc[valid_rows, valid_cols]

    # Visual settings
    plt.figure(figsize=(10, 8))
    sns.heatmap(pivot_table, annot=True, fmt="g", cmap="YlOrRd", cbar=True, 
                linewidths=.5, square=True)
    
    plt.title("Data Analyst Job Market in North Italy:\nLanguage Requirements Matrix", 
              fontsize=16, pad=20, fontweight='bold')
    plt.xlabel("English Level (CEFR)", fontsize=12, fontweight='bold')
    plt.ylabel("Italian Level (CEFR)", fontsize=12, fontweight='bold')
    
    # Invert Y-axis so 'Not Spec' is at the bottom and 'C2' at the top
    plt.gca().invert_yaxis()