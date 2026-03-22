import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

def get_language_data(cursor, lang_prefix):
    query = f"""
    SELECT 
        COALESCE({lang_prefix}_level, 'Not Spec') AS Level,
        CASE 
            WHEN {lang_prefix}_status LIKE '%Mandatory%' THEN 'Mandatory'
            WHEN {lang_prefix}_status LIKE '%Plus%' OR {lang_prefix}_status LIKE '%Optional%' THEN 'Optional / Plus'
            ELSE 'Not Mentioned / Not Required'
        END AS Status,
        COUNT(*) AS Vacancies
    FROM jobs
    GROUP BY Level, Status
    """
    df = pd.read_sql_query(query, cursor.connection)
    pivot_df = df.pivot(index='Level', columns='Status', values='Vacancies').fillna(0)
    
    order = ['Not Spec', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    valid_rows = [r for r in order if r in pivot_df.index]
    return pivot_df.loc[valid_rows]

def generate_dual_status_chart(db_path='glassdoor_jobs.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    df_eng = get_language_data(cursor, 'english')
    df_ita = get_language_data(cursor, 'italian')
    conn.close()

    colors = {
        'Mandatory': '#b2182b', 
        'Optional / Plus': '#4393c3',
        'Not Mentioned / Not Required': '#d9d9d9'
    }

    # Create a canvas with two subplots (1 row, 2 columns)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), sharey=True)

    # Plotting function for each chart
    def plot_chart(df, ax, title):
        plot_colors = [colors[col] for col in df.columns if col in colors]
        df.plot(kind='bar', stacked=True, color=plot_colors, ax=ax, edgecolor='black', linewidth=0.5, legend=False)
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel('CEFR Level', fontsize=12, fontweight='bold')
        ax.tick_params(axis='x', rotation=0)
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Add total sum labels on top of columns
        for i, total in enumerate(df.sum(axis=1)):
            if total > 0:
                ax.text(i, total + 1, str(int(total)), ha='center', fontweight='bold', fontsize=10)

    # Draw left (English) and right (Italian) charts
    plot_chart(df_eng, axes[0], 'English Requirements')
    plot_chart(df_ita, axes[1], 'Italian Requirements')

    axes[0].set_ylabel('Number of Vacancies', fontsize=12, fontweight='bold')

    # Shared legend
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 1.1), 
               ncol=3, title='Requirement Criticality', fontsize=11, title_fontsize=12)

    plt.tight_layout()
    plt.savefig('dual_language_status.png', dpi=300, bbox_inches='tight')
    print("[+] Dual status chart generated: dual_language_status.png")

if __name__ == '__main__':
    generate_dual_status_chart()