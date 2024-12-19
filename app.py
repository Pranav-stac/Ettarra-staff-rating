from flask import Flask, render_template, request, flash, send_file
import pandas as pd
import io
import base64
import matplotlib.pyplot as plt
from main import process_ratings
import logging

app = Flask(__name__)
app.secret_key = 'ettarra_coffee_house_2024'  # Required for flash messages

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected')
            return render_template('index.html')
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return render_template('index.html')

        if file and allowed_file(file.filename):
            try:
                # Read the file
                df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
                
                # Process the data and get results
                results_df, plot_base64 = process_ratings(df)
                
                return render_template('results.html', 
                                     tables=[results_df.to_html(classes='data-table', index=False)],
                                     plot=plot_base64)
            except Exception as e:
                logging.error(f"Error processing file: {e}")
                flash(f'Error processing file: {str(e)}')
                return render_template('index.html')
        else:
            flash('Only CSV and Excel files are allowed')
            return render_template('index.html')

    return render_template('index.html')

@app.route('/manual-entry', methods=['GET', 'POST'])
def manual_entry():
    if request.method == 'POST':
        try:
            # Get staff count from form
            staff_count = int(request.form.get('staff_count', 0))
            
            if staff_count > 0:
                # Create DataFrame from form data
                names = []
                ratings_data = []
                
                for i in range(staff_count):
                    name = request.form.get(f'name_{i}')
                    names.append(name)
                    row = []
                    for j in range(staff_count):
                        rating = float(request.form.get(f'rating_{i}_{j}', 0))
                        row.append(rating)
                    ratings_data.append(row)
                
                # Create DataFrame
                df = pd.DataFrame(ratings_data, columns=names)
                df.insert(0, 'Staff', names)
                
                # Process the data
                results_df, plot_base64 = process_ratings(df)
                
                if 'export_excel' in request.form:
                    # Create Excel file in memory
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        results_df.to_excel(writer, sheet_name='Results', index=False)
                    output.seek(0)
                    
                    return send_file(
                        output,
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True,
                        download_name='staff_ratings_results.xlsx'
                    )
                
                return render_template('results.html', 
                                    tables=[results_df.to_html(classes='data-table', index=False)],
                                    plot=plot_base64)
                                    
        except Exception as e:
            logging.error(f"Error processing manual entry: {e}")
            flash(f'Error processing data: {str(e)}')
            return render_template('manual_entry.html')
    
    return render_template('manual_entry.html')

def allowed_file(filename):
    return filename.endswith(('.csv', '.xlsx', '.xls'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6060, debug=True)