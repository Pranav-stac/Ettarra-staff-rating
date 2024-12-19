import matplotlib
matplotlib.use('Agg')
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys
import logging
import io
import base64
from flask import Flask, render_template, request, session, redirect, url_for
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_elo_rating(rating_a, rating_b, k_factor=32):
    """Calculate Elo rating changes with modified scoring"""
    # Calculate expected scores
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    expected_b = 1 - expected_a
    
    # Use absolute ratings instead of comparative scores
    actual_score = rating_a / 10  # Now higher ratings = higher score
    
    # Calculate rating changes
    change_a = k_factor * (actual_score - expected_a)
    change_b = k_factor * ((rating_b/10) - expected_b)
    
    return change_a, change_b

def process_ratings(df):
    try:
        # Ensure the first column is renamed to 'Staff'
        df = df.copy()
        df.columns = ['Staff'] + list(df.columns[1:])
        
        names = df['Staff'].tolist()
        ratings = {name: 1500 for name in names}
        
        # Adjust K-factor based on rating difference
        BASE_K = 32
        
        for rater in names:
            for ratee in names:
                if rater != ratee:
                    try:
                        rating_given = float(df.loc[df['Staff'] == rater, ratee].iloc[0])
                        rating_received = float(df.loc[df['Staff'] == ratee, rater].iloc[0])
                        
                        # Adjust K based on rating difference
                        rating_diff = abs(rating_given - rating_received)
                        K = BASE_K * (1 + rating_diff / 10)
                        
                        # Calculate expected score
                        expected_score = 1 / (1 + 10 ** ((ratings[ratee] - ratings[rater]) / 400))
                        
                        # Calculate actual score based on normalized ratings
                        actual_score = rating_given / 10  # Normalize to 0-1 scale
                        
                        # Update Elo ratings with weighted updates
                        ratings[rater] += K * (actual_score - expected_score)
                        ratings[ratee] += K * ((rating_received/10) - (1 - expected_score))
                    except Exception as e:
                        logging.error(f"Error processing ratings for {rater} -> {ratee}: {e}")
                        raise
        
        # Adjust final ratings based on self-ratings (20%) and others' average (80%)
        results = []
        for name in names:
            try:
                self_rating = float(df.loc[df['Staff'] == name, name].iloc[0])
                others_ratings = [float(df.loc[df['Staff'] == other, name].iloc[0]) 
                                for other in names if other != name]
                others_avg = sum(others_ratings) / len(others_ratings)
                
                # Apply adjustments with new weights
                final_rating = ratings[name]
                final_rating = final_rating * (0.8 + 0.2 * (self_rating / 10))  # Self rating 20%
                final_rating = final_rating * (0.8 + 0.2 * (others_avg / 10))   # Others rating 20%
                
                results.append({
                    'Name': name,
                    'SelfRating': self_rating,
                    'OthersAverageRating': others_avg,
                    'EloRating': final_rating,
                    'Difference': final_rating - self_rating
                })
            except Exception as e:
                logging.error(f"Error processing results for {name}: {e}")
                raise
        
        # Create results DataFrame
        results_df = pd.DataFrame(results)
        results_df['Rank'] = results_df['EloRating'].rank(ascending=False, method='min').astype(int)
        results_df = results_df.sort_values('Rank')
        
        # Create visualization
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 15))
        
        # Plot 1: Ratings Comparison
        x = np.arange(len(results_df))
        width = 0.35
        
        ax1.bar(x - width/2, results_df['SelfRating'], width, 
               label='Self Rating', color='skyblue')
        ax1.bar(x + width/2, results_df['OthersAverageRating'], width, 
               label='Others Average Rating', color='lightgreen')
        
        ax1.set_ylabel('Ratings')
        ax1.set_title('Staff Ratings Comparison')
        ax1.set_xticks(x)
        ax1.set_xticklabels(results_df['Name'], rotation=45, ha='right')
        ax1.legend()
        ax1.grid(True, linestyle='--', alpha=0.7)
        
        # Add value labels
        for i, v in enumerate(results_df['SelfRating']):
            ax1.text(i - width/2, v, str(round(v, 2)), ha='center', va='bottom')
        for i, v in enumerate(results_df['OthersAverageRating']):
            ax1.text(i + width/2, v, str(round(v, 2)), ha='center', va='bottom')
        
        # Plot 2: Elo Ratings
        ax2.bar(x, results_df['EloRating'], color='orange')
        ax2.set_ylabel('Elo Rating')
        ax2.set_title('Staff Elo Ratings')
        ax2.set_xticks(x)
        ax2.set_xticklabels(results_df['Name'], rotation=45, ha='right')
        ax2.grid(True, linestyle='--', alpha=0.7)
        
        # Add value labels for Elo
        for i, v in enumerate(results_df['EloRating']):
            ax2.text(i, v, str(round(v, 1)), ha='center', va='bottom')
        
        plt.tight_layout()
        
        # Save plot to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight')
        buffer.seek(0)
        plot_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return results_df, plot_base64
        
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        raise

if __name__ == "__main__":
    # Allow command-line arguments for file path
    file_path = sys.argv[1] 
    main(file_path)