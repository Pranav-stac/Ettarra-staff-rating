import matplotlib
matplotlib.use('Agg')
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys
import logging
import io
import base64

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def process_ratings(df):
    """Process peer ratings matrix format"""
    try:
        # Get list of names (column headers excluding first column)
        names = df.columns[1:].tolist()
        
        # Create a new DataFrame for results
        results_df = pd.DataFrame()
        results_df['Name'] = names
        
        # Extract self ratings from diagonal
        self_ratings = []
        for i, name in enumerate(names):
            self_ratings.append(df.iloc[i, i+1])  # +1 because first column is names
        results_df['SelfRating'] = self_ratings
        
        # Calculate others' average ratings (excluding self)
        others_ratings = []
        for i, name in enumerate(names):
            # Get all ratings for this person (excluding their self-rating)
            person_ratings = df.iloc[:, i+1].tolist()  # +1 because first column is names
            # Remove self-rating from the list
            del person_ratings[i]
            # Calculate average of others' ratings
            others_ratings.append(sum(person_ratings) / len(person_ratings))
        results_df['OthersAverageRating'] = others_ratings
        
        # Calculate remaining metrics
        results_df['Difference'] = results_df['SelfRating'] - results_df['OthersAverageRating']
        
        weight_self = 0.3
        weight_others = 0.7
        results_df['WeightedScore'] = (weight_self * results_df['SelfRating']) + \
                                      (weight_others * results_df['OthersAverageRating'])
        results_df['Rank'] = results_df['WeightedScore'].rank(ascending=False)
        
        # Sort by rank for display
        results_df = results_df.sort_values(by='Rank')
                # Create visualization
        fig, ax1 = plt.subplots(figsize=(15, 10))
        
        # Plot bars for Self Rating and Others Average Rating
        x = np.arange(len(results_df))
        width = 0.35
        
        ax1.bar(x - width/2, results_df['SelfRating'], width, 
               label='Self Rating', color='skyblue')
        ax1.bar(x + width/2, results_df['OthersAverageRating'], width, 
               label='Others Average Rating', color='lightgreen')
        
        # Customize the plot
        ax1.set_ylabel('Ratings')
        ax1.set_title('Staff Performance Ratings Comparison')
        ax1.set_xticks(x)
        ax1.set_xticklabels(results_df['Name'], rotation=45, ha='right')
        ax1.legend()
        ax1.grid(True, linestyle='--', alpha=0.7)
        
        # Add value labels on top of bars
        for i, v in enumerate(results_df['SelfRating']):
            ax1.text(i - width/2, v, str(round(v, 2)), ha='center', va='bottom')
        for i, v in enumerate(results_df['OthersAverageRating']):
            ax1.text(i + width/2, v, str(round(v, 2)), ha='center', va='bottom')
            
        # Adjust layout to prevent label cutoff
        plt.tight_layout()
        
        # Save plot to base64 string for web display
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight')
        buffer.seek(0)
        plot_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()

        return results_df, plot_base64

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        raise e

if __name__ == "__main__":
    # Allow command-line arguments for file path
    file_path = sys.argv[1] 
    main(file_path)