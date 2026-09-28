import os
import time
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import urllib.parse
import zipfile
import tempfile

app = Flask(__name__)
# Allow your Vercel frontend to communicate with this Render backend
CORS(app) 
scraper = cloudscraper.create_scraper()

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({"status": "online", "message": "Backend is running on Render!"})

@app.route('/api/download', methods=['POST'])
def download_songs():
    if 'file' not in request.files:
        return jsonify({'error': 'No CSV file uploaded'}), 400
        
    file = request.files['file']
    
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = os.path.join(temp_dir, "input.csv")
        file.save(csv_path)
        
        try:
            df = pd.read_csv(csv_path)
            movie_col = next((c for c in df.columns if 'movie' in c.lower()), df.columns[0])
            song_col = next((c for c in df.columns if 'song' in c.lower()), None)
            
            zip_path = os.path.join(temp_dir, "songs.zip")
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for index, row in df.iterrows():
                    movie = str(row[movie_col]).strip()
                    song = str(row[song_col]).strip() if song_col and pd.notna(row[song_col]) else ""
                    
                    if not movie or movie.lower() == 'nan':
                        continue
                        
                    search_url = f"https://www.masstamilan.dev/search?keyword={urllib.parse.quote(movie)}"
                    res = scraper.get(search_url)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    
                    movie_link = None
                    for a in soup.find_all('a', href=True):
                        if '-songs' in a['href']:
                            movie_link = "https://www.masstamilan.dev" + a['href']
                            break
                            
                    if not movie_link:
                        continue
                        
                    res = scraper.get(movie_link)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    
                    for a in soup.find_all('a', href=True):
                        if 'd320_cdn' in a['href']:
                            tr = a.find_parent('tr')
                            title = "Unknown"
                            if tr:
                                td = tr.find('td')
                                if td:
                                    h2 = td.find('h2') or td.find('a')
                                    if h2:
                                        title = h2.text.strip()
                                        
                            if song and song.lower() not in title.lower():
                                continue
                                
                            clean_title = "".join(x for x in title if x.isalnum() or x in " -_")
                            
                            try:
                                mp3_res = scraper.get(a['href'])
                                mp3_path = os.path.join(temp_dir, f"{clean_title}.mp3")
                                with open(mp3_path, 'wb') as f:
                                    f.write(mp3_res.content)
                                
                                # Add file to zip archive
                                zipf.write(mp3_path, f"{clean_title}.mp3")
                            except Exception as e:
                                print(f"Error downloading {clean_title}: {e}")
                                
                            time.sleep(0.5)
            
            if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
                return jsonify({'error': 'No songs were found or downloaded. Cloudflare might be blocking Render.'}), 400
                
            return send_file(zip_path, as_attachment=True, download_name="masstamilan_songs.zip")
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
