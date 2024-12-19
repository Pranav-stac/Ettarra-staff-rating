from flask import Flask, render_template, request, flash
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

def allowed_file(filename):
    return filename.endswith(('.csv', '.xlsx', '.xls'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6060, debug=True)