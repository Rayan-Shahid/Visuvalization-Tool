import os
import pandas as pd
from flask import Flask, render_template, request
from collections import defaultdict
import re

app = Flask(__name__)

# Map month names to filenames
MONTH_MAP = {
    'jan': 'Jan.xlsx',
    'feb': 'Feb.xlsx',
    'mar': 'Mar.xlsx',
    'apr': 'Apr.xlsx',
    'may': 'May.xlsx',
    'jun': 'Jun.xlsx',
    'jul': 'Jul.xlsx',
    'aug': 'Aug.xlsx',
    'sep': 'Sep.xlsx',
    'oct': 'Oct.xlsx',
    'nov': 'Nov.xlsx',
    'dec': 'Dec.xlsx'
}

# Financial metrics to track in specific order
METRICS = ['Sales', 'Refund', 'Discount', 'Promotion', 'Net Sales']

def custom_store_sort(store):
    """
    Custom sorting for store names
    Prioritizes specific ordering: Big Jims, NP 1, NP 2, etc.
    """
    if store == 'Big Jims':
        return (0, store)
    
    # Match NP followed by a number
    np_match = re.match(r'^NP (\d+)$', store)
    if np_match:
        return (1, int(np_match.group(1)))
    
    # All other stores come last, sorted alphabetically
    return (2, store)

def get_all_stores():
    """
    Retrieve unique store names from all monthly Excel files
    with custom sorting
    """
    stores = set()
    for month, file_name in MONTH_MAP.items():
        file_path = os.path.join('excel_files', file_name)
        try:
            xls = pd.ExcelFile(file_path)
            stores.update(xls.sheet_names)
        except FileNotFoundError:
            print(f"File not found: {file_name}")
        except Exception as e:
            print(f"Error reading {file_name}: {e}")
    
    # Sort stores using custom sorting logic
    return sorted(list(stores), key=custom_store_sort)

@app.route('/', methods=['GET', 'POST'])
def sales_dashboard():
    error = None
    dept_metrics = {}  # Structure: {dept: {'Sales': val, 'Discount': val, ...}}
    store_metrics = {}  # Structure: {store: {'Sales': val, 'Discount': val, ...}}
    accessed_files = []
    view_type = "department"  # Default view
    time_period = ""
    
    # Available months and stores for dropdown
    months = list(MONTH_MAP.keys())
    stores = get_all_stores()

    if request.method == 'POST':
        start_month = request.form.get('start_month', '').lower()
        end_month = request.form.get('end_month', '').lower()
        selected_store = request.form.get('store', '')

        # Validate input
        if not start_month or not end_month:
            error = "Please select start and end months"
            return render_template('index.html', months=months, stores=stores, error=error)

        try:
            # Get month indices
            start_idx = months.index(start_month)
            end_idx = months.index(end_month)

            if start_idx > end_idx:
                error = "Start month must be before or equal to end month"
                return render_template('index.html', months=months, stores=stores, error=error)

            # Select months in range (inclusive)
            selected_months = months[start_idx:end_idx + 1]
            
            # Create a list of unique months to process (avoid duplicates)
            selected_months = list(dict.fromkeys(selected_months))
            
            # Display time range in a friendly format
            time_period = "for " + start_month.capitalize()
            if start_month != end_month:
                time_period = f"from {start_month.capitalize()} to {end_month.capitalize()}"
            
            # Track unique accessed months to avoid duplicates in display
            accessed_months = set()

            # Process based on whether a specific store is selected
            if selected_store:
                view_type = "department"
                # Store financial metrics per department for the selected store
                dept_metrics = defaultdict(lambda: {metric: 0.0 for metric in METRICS})
                
                # Process each selected file
                for month in selected_months:
                    file_name = MONTH_MAP[month]
                    file_path = os.path.join('excel_files', file_name)

                    try:
                        # Read Excel file
                        xls = pd.ExcelFile(file_path)
                    except FileNotFoundError:
                        error = f"File not found: {file_name}"
                        continue

                    # Check if selected store exists in this month's workbook
                    if selected_store not in xls.sheet_names:
                        continue

                    # Track accessed files (prevent duplicates)
                    if month.capitalize() not in accessed_months:
                        accessed_files.append(month.capitalize())
                        accessed_months.add(month.capitalize())

                    # Read the specific store's sheet
                    try:
                        df = pd.read_excel(xls, sheet_name=selected_store)
                    except Exception as e:
                        error = f"Failed to read sheet {selected_store} in {file_name}: {e}"
                        continue

                    # Skip if required columns are missing
                    if 'Dept Name' not in df.columns:
                        continue

                    # Clean and process data
                    df = df.dropna(subset=['Dept Name'])
                    df['Dept Name'] = df['Dept Name'].str.strip().str.lower()

                    # Aggregate metrics by department
                    for _, row in df.iterrows():
                        dept = row['Dept Name']
                        
                        # Process each metric
                        for metric in METRICS:
                            if metric in df.columns:
                                value = row.get(metric, 0)
                                if pd.notna(value):
                                    dept_metrics[dept][metric] += value

                # Calculate Net Sales if not already present
                for dept, metrics in dept_metrics.items():
                    if 'Net Sales' not in metrics or pd.isna(metrics['Net Sales']):
                        metrics['Net Sales'] = metrics.get('Sales', 0) - metrics.get('Refund', 0) - metrics.get('Discount', 0) + metrics.get('Promotion', 0)
                
                # Sort departments by sales (descending)
                sorted_depts = sorted(dept_metrics.keys(), 
                                      key=lambda x: dept_metrics[x]['Sales'], 
                                      reverse=True)
                dept_metrics = {dept: dept_metrics[dept] for dept in sorted_depts}

                # Additional error handling for no data found
                if not dept_metrics:
                    error = f"No data found for {selected_store} in the selected months"

            else:
                # No store selected - show totals for all stores
                view_type = "store"
                store_metrics = defaultdict(lambda: {metric: 0.0 for metric in METRICS})
                
                # Process each selected month
                for month in selected_months:
                    file_name = MONTH_MAP[month]
                    file_path = os.path.join('excel_files', file_name)

                    try:
                        # Read Excel file
                        xls = pd.ExcelFile(file_path)
                        
                        # Track accessed files (prevent duplicates)
                        if month.capitalize() not in accessed_months:
                            accessed_files.append(month.capitalize())
                            accessed_months.add(month.capitalize())
                    except FileNotFoundError:
                        error = f"File not found: {file_name}"
                        continue

                    # For each store name in the worksheet
                    for store_name in xls.sheet_names:
                        try:
                            df = pd.read_excel(xls, sheet_name=store_name)
                        except Exception as e:
                            continue

                        # Skip if no relevant metrics columns are found
                        if not any(metric in df.columns for metric in METRICS):
                            continue

                        # Process each metric for this store
                        for metric in METRICS:
                            if metric in df.columns:
                                metric_sum = df[metric].sum()
                                if pd.notna(metric_sum):
                                    store_metrics[store_name][metric] += metric_sum

                # Calculate Net Sales if not already present
                for store, metrics in store_metrics.items():
                    if 'Net Sales' not in metrics or pd.isna(metrics['Net Sales']):
                        metrics['Net Sales'] = metrics.get('Sales', 0) - metrics.get('Refund', 0) - metrics.get('Discount', 0) + metrics.get('Promotion', 0)
                
                # Sort stores using custom sort for display
                sorted_stores = sorted(store_metrics.keys(), key=custom_store_sort)
                store_metrics = {store: store_metrics[store] for store in sorted_stores}

                # Additional error handling for no data found
                if not store_metrics:
                    error = "No data found for any store in the selected months"

        except Exception as e:
            error = f"An unexpected error occurred: {str(e)}"

    return render_template('index.html', months=months, stores=stores, 
                           dept_metrics=dept_metrics, store_metrics=store_metrics,
                           metrics=METRICS, error=error, accessed_files=accessed_files,
                           view_type=view_type, time_period=time_period)

if __name__ == '__main__':
    app.run(debug=True)