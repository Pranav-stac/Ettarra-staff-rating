from flask import Flask, render_template, request, flash, send_file, jsonify, session, redirect, url_for
import pandas as pd
import io
import base64
import matplotlib.pyplot as plt
from main import process_ratings
import logging
import random
import numpy as np
import seaborn 
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'ettarra_coffee_house_2024'

def init_db():
    conn = sqlite3.connect('ratings.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS ratings_sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT UNIQUE,
                  created_at TIMESTAMP,
                  is_manual BOOLEAN)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ratings_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT,
                  staff_name TEXT,
                  self_rating REAL,
                  elo_rating REAL,
                  others_avg_rating REAL,
                  rank INTEGER,
                  FOREIGN KEY(session_id) REFERENCES ratings_sessions(session_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS individual_ratings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT,
                  rater TEXT,
                  ratee TEXT,
                  rating REAL,
                  reason TEXT,
                  FOREIGN KEY(session_id) REFERENCES ratings_sessions(session_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS plots
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT UNIQUE,
                  plot_data TEXT,
                  FOREIGN KEY(session_id) REFERENCES ratings_sessions(session_id))''')
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect('ratings.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialize database when app starts
with app.app_context():
    init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx', 'xls'}

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return render_template('index.html')

        if file and allowed_file(file.filename):
            try:
                df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
                results_df, plot_base64 = process_ratings(df)
                
                # Generate unique session ID
                session_id = datetime.now().strftime('%Y%m%d%H%M%S')
                
                # Store in database
                conn = get_db()
                c = conn.cursor()
                
                # Create session
                c.execute('INSERT INTO ratings_sessions (session_id, created_at, is_manual) VALUES (?, ?, ?)',
                         (session_id, datetime.now(), False))
                
                # Store ratings data
                for _, row in results_df.iterrows():
                    c.execute('''INSERT INTO ratings_data 
                                (session_id, staff_name, self_rating, elo_rating, others_avg_rating, rank)
                                VALUES (?, ?, ?, ?, ?, ?)''',
                             (session_id, row['Name'], row['SelfRating'], 
                              row['EloRating'], row['OthersAverageRating'], row['Rank']))
                
                # Store plot
                c.execute('INSERT INTO plots (session_id, plot_data) VALUES (?, ?)',
                         (session_id, plot_base64))
                
                conn.commit()
                conn.close()
                
                # Store session_id in flask session
                session['current_session'] = session_id
                
                return redirect(url_for('show_results'))
                
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
        staff_count = int(request.form.get('staff_count', 0))
        if 1 <= staff_count <= 20:
            session['staff_count'] = staff_count
            return render_template('manual_entry.html', 
                                step='names', 
                                staff_count=staff_count)
        else:
            flash('Please enter a valid number of staff (1-20)')
    
    return render_template('manual_entry.html', step='initial')

@app.route('/submit-names', methods=['POST'])
def submit_names():
    staff_count = session.get('staff_count', 0)
    if not staff_count:
        return redirect(url_for('manual_entry'))
    
    # Collect names
    names = []
    for i in range(staff_count):
        name = request.form.get(f'name_{i}')
        if name:
            names.append(name.strip())
    
    if len(names) != staff_count:
        flash('Please fill in all names')
        return render_template('manual_entry.html', 
                             step='names', 
                             staff_count=staff_count)
    
    # Create new session in database
    session_id = datetime.now().strftime('%Y%m%d%H%M%S')
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Store session
        c.execute('INSERT INTO ratings_sessions (session_id, created_at, is_manual) VALUES (?, ?, ?)',
                 (session_id, datetime.now(), True))
        
        # Store staff names temporarily
        session['staff_names'] = names
        session['current_session'] = session_id
        session['remaining_raters'] = names.copy()
        
        conn.commit()
        
        # Select first random rater
        current_rater = random.choice(session['remaining_raters'])
        session['remaining_raters'].remove(current_rater)
        
        return render_template('manual_entry.html',
                             step='rating',
                             current_rater=current_rater,
                             other_staff=[n for n in names if n != current_rater])
    except Exception as e:
        conn.rollback()
        logging.error(f"Error in submit_names: {e}")
        flash('Error starting rating process')
        return redirect(url_for('manual_entry'))
    finally:
        conn.close()

@app.route('/submit-ratings', methods=['POST'])
def submit_ratings():
    current_rater = request.form.get('current_rater')
    session_id = session.get('current_session')
    
    if not current_rater or not session_id:
        return redirect(url_for('manual_entry'))
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Store individual ratings
        self_rating = float(request.form.get('self_rating'))
        self_reason = request.form.get('self_reason', '')
        
        # Store self rating
        c.execute('''INSERT INTO individual_ratings 
                    (session_id, rater, ratee, rating, reason)
                    VALUES (?, ?, ?, ?, ?)''',
                 (session_id, current_rater, current_rater, self_rating, self_reason))
        
        # Store ratings for others
        for name in session['staff_names']:
            if name != current_rater:
                rating = float(request.form.get(f'rating_{name}'))
                reason = request.form.get(f'reason_{name}', '')
                c.execute('''INSERT INTO individual_ratings 
                            (session_id, rater, ratee, rating, reason)
                            VALUES (?, ?, ?, ?, ?)''',
                         (session_id, current_rater, name, rating, reason))
        
        conn.commit()
        
        # Check if all ratings are complete
        if not session.get('remaining_raters'):
            return process_final_manual_ratings(session_id)
        
        # Select next random rater
        remaining_raters = session.get('remaining_raters', [])
        if remaining_raters:
            current_rater = random.choice(remaining_raters)
            remaining_raters.remove(current_rater)
            session['remaining_raters'] = remaining_raters
            
            return render_template('manual_entry.html',
                                step='rating',
                                current_rater=current_rater,
                                other_staff=[n for n in session['staff_names'] if n != current_rater])
        else:
            return process_final_manual_ratings(session_id)
                             
    except Exception as e:
        conn.rollback()
        logging.error(f"Error in submit_ratings: {e}")
        flash('Error submitting ratings')
        return redirect(url_for('manual_entry'))
    finally:
        conn.close()

def process_final_manual_ratings(session_id):
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Get all ratings
        c.execute('''SELECT rater, ratee, rating 
                    FROM individual_ratings 
                    WHERE session_id = ?''', (session_id,))
        ratings = c.fetchall()
        
        # Create DataFrame from ratings
        data = []
        names = session['staff_names']
        
        for rater in names:
            row = [rater]
            for ratee in names:
                rating = next((r['rating'] for r in ratings 
                             if r['rater'] == rater and r['ratee'] == ratee), 0)
                row.append(rating)
            data.append(row)
        
        df = pd.DataFrame(data, columns=['Staff'] + names)
        results_df, plot_base64 = process_ratings(df)
        
        # Store results in database
        for _, row in results_df.iterrows():
            c.execute('''INSERT INTO ratings_data 
                        (session_id, staff_name, self_rating, elo_rating, others_avg_rating, rank)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (session_id, row['Name'], row['SelfRating'], 
                      row['EloRating'], row['OthersAverageRating'], row['Rank']))
        
        # Store plot
        c.execute('INSERT INTO plots (session_id, plot_data) VALUES (?, ?)',
                 (session_id, plot_base64))
        
        conn.commit()
        
        # Clear session except for current_session
        session.clear()
        session['current_session'] = session_id
        
        return redirect(url_for('show_results'))
        
    except Exception as e:
        conn.rollback()
        logging.error(f"Error in process_final_manual_ratings: {e}")
        flash('Error processing final ratings')
        return redirect(url_for('manual_entry'))
    finally:
        conn.close()

@app.route('/process-ratings', methods=['POST'])
def process_sequential_ratings():
    try:
        data = request.json
        ratings_matrix = data['ratings']
        reasons = data['reasons']  # Store this if you want to save the reasons
        
        # Convert matrix to DataFrame
        df = pd.DataFrame(ratings_matrix[1:], columns=ratings_matrix[0])
        
        # Process ratings
        results_df, plot_base64 = process_ratings(df)
        
        # Convert DataFrame to list of dictionaries
        results_data = results_df.to_dict('records')
        
        # Store results in session
        session['ratings_data'] = df.to_json()
        session['last_results'] = {
            'elo_ratings': results_df['EloRating'].to_dict(),
            'staff_names': df['Name'].tolist(),
            'plot': plot_base64,
            'results_data': results_data
        }
        
        # Return redirect URL
        return jsonify({'redirect': url_for('show_results')})
        
    except Exception as e:
        logging.error(f"Error processing sequential ratings: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/show-results')
def show_results():
    session_id = session.get('current_session')
    if not session_id:
        flash('No results found. Please upload a file or enter ratings manually.')
        return redirect(url_for('upload_file'))
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Get ratings data
        c.execute('''SELECT rd.*, p.plot_data 
                    FROM ratings_data rd 
                    LEFT JOIN plots p ON rd.session_id = p.session_id 
                    WHERE rd.session_id = ? 
                    ORDER BY rd.rank''', (session_id,))
        ratings_data = c.fetchall()
        
        # Get plot data
        c.execute('SELECT plot_data FROM plots WHERE session_id = ?', (session_id,))
        plot_data = c.fetchone()
        
        if not ratings_data:
            flash('No results found. Please upload a file or enter ratings manually.')
            return redirect(url_for('upload_file'))
        
        # Convert to list of dictionaries
        results_data = [{
            'Rank': row['rank'],
            'Name': row['staff_name'],
            'EloRating': round(row['elo_rating'], 2),
            'SelfRating': round(row['self_rating'], 2),
            'OthersAverageRating': round(row['others_avg_rating'], 2),
            'Difference': round(row['elo_rating'] - row['self_rating'], 2)
        } for row in ratings_data]
        
        conn.close()
        
        return render_template('results.html',
                             results_data=results_data,
                             plot=plot_data['plot_data'] if plot_data else '',
                             staff_names=[r['staff_name'] for r in ratings_data])
                             
    except Exception as e:
        logging.error(f"Error showing results: {e}")
        flash('Error loading results. Please try again.')
        return redirect(url_for('upload_file'))

@app.route('/staff/<name>')
def staff_details(name):
    session_id = session.get('current_session')
    if not session_id:
        flash('No results data found. Please upload a file or enter ratings manually.')
        return redirect(url_for('upload_file'))
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Get session info
        c.execute('SELECT is_manual FROM ratings_sessions WHERE session_id = ?', (session_id,))
        session_info = c.fetchone()
        
        if not session_info:
            flash('Session not found.')
            return redirect(url_for('upload_file'))
        
        # Get staff details
        c.execute('''SELECT * FROM ratings_data 
                    WHERE session_id = ? AND staff_name = ?''', 
                    (session_id, name))
        staff_data = c.fetchone()
        
        if not staff_data:
            flash('Staff member not found.')
            return redirect(url_for('show_results'))
        
        # Get individual ratings
        c.execute('''SELECT rater, rating, reason 
                    FROM individual_ratings 
                    WHERE session_id = ? AND ratee = ?''',
                    (session_id, name))
        ratings_received = c.fetchall()
        
        c.execute('''SELECT ratee, rating, reason 
                    FROM individual_ratings 
                    WHERE session_id = ? AND rater = ?''',
                    (session_id, name))
        ratings_given = c.fetchall()
        
        # Format ratings details
        ratings_received_details = [{
            'name': r['rater'],
            'rating': round(r['rating'], 2),
            'reason': r['reason'] or 'N/A'
        } for r in ratings_received]
        
        ratings_given_details = [{
            'name': r['ratee'],
            'rating': round(r['rating'], 2),
            'reason': r['reason'] or 'N/A'
        } for r in ratings_given]
        
        # Sort ratings by value
        ratings_received_details = sorted(ratings_received_details, 
                                       key=lambda x: x['rating'], 
                                       reverse=True)
        ratings_given_details = sorted(ratings_given_details, 
                                     key=lambda x: x['rating'], 
                                     reverse=True)
        
        # Calculate averages
        avg_rating_received = np.mean([r['rating'] for r in ratings_received_details]) if ratings_received_details else 0
        avg_rating_given = np.mean([r['rating'] for r in ratings_given_details]) if ratings_given_details else 0
        
        # Prepare staff stats
        staff_stats = {
            'name': name,
            'ratings_received_details': ratings_received_details,
            'ratings_given_details': ratings_given_details,
            'self_rating': staff_data['self_rating'],
            'average_rating_received': round(avg_rating_received, 2),
            'average_rating_given': round(avg_rating_given, 2),
            'elo_rating': round(staff_data['elo_rating'], 2)
        }
        
        # Get plot
        c.execute('SELECT plot_data FROM plots WHERE session_id = ?', (session_id,))
        plot_data = c.fetchone()
        
        conn.close()
        
        return render_template('staff_details.html',
                             stats=staff_stats,
                             plot=plot_data['plot_data'] if plot_data else '')
                             
    except Exception as e:
        logging.error(f"Error in staff_details: {e}")
        flash('Error loading staff details')
        return redirect(url_for('show_results'))

@app.route('/debug-table')
def debug_table():
    if 'staff_names' not in session:
        return "No staff names in session"
    return f"""
    Staff names in session: {session['staff_names']}
    <br>
    Sample link: {url_for('staff_details', name=session['staff_names'][0])}
    """

@app.route('/past-sessions')
def past_sessions():
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Get all sessions with basic stats
        c.execute('''
            SELECT 
                rs.session_id,
                rs.created_at,
                rs.is_manual,
                COUNT(DISTINCT rd.staff_name) as staff_count,
                MIN(rd.rank) as top_rank,
                MAX(rd.rank) as bottom_rank
            FROM ratings_sessions rs
            JOIN ratings_data rd ON rs.session_id = rd.session_id
            GROUP BY rs.session_id
            ORDER BY rs.created_at DESC
        ''')
        
        sessions = []
        for row in c.fetchall():
            # Get top performer
            c.execute('''
                SELECT staff_name, elo_rating 
                FROM ratings_data 
                WHERE session_id = ? AND rank = ?
            ''', (row['session_id'], row['top_rank']))
            top_performer = c.fetchone()
            
            sessions.append({
                'id': row['session_id'],
                'date': datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M'),
                'type': 'Manual Entry' if row['is_manual'] else 'File Upload',
                'staff_count': row['staff_count'],
                'top_performer': top_performer['staff_name'],
                'top_rating': round(top_performer['elo_rating'], 1)
            })
        
        conn.close()
        return render_template('past_sessions.html', sessions=sessions)
        
    except Exception as e:
        logging.error(f"Error loading past sessions: {e}")
        flash('Error loading session history')
        return redirect(url_for('upload_file'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6060, debug=True)