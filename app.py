import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from urllib.parse import urlparse
from flask_cors import CORS

from flask import Flask, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='static')
CORS(app)

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/download', methods=['POST'])
def download_images():
    data = request.get_json()
    url = data.get('url')

    try:
        html = requests.get(url).text
        soup = BeautifulSoup(html, 'html.parser')

        # Extract folder name from <div class="pb-2"> a tags
        name_parts = [a.text.strip() for div in soup.find_all('div', class_='pb-2') for a in div.find_all('a') if a.text.strip()]
        folder_name = " - ".join(name_parts).replace(":", "").replace("/", " ")
        if not folder_name:
            folder_name = "ImageGallery"

        # Create folder
        save_path = os.path.join("downloads", folder_name)
        os.makedirs(save_path, exist_ok=True)

        # Find base image link
        photo_div = soup.find('div', class_='d-flex justify-content-center photo-item')
        if not photo_div:
            return jsonify({"error": "Could not find image preview link."}), 400

        href = photo_div.find('a')['href']
        base_url = href.rsplit('/', 1)[0] + '/'

        # Find image count from <h1> using regex
        h1 = soup.find('h1', class_='container text-center text-uppercase h6 mt-2')
        if not h1:
            return jsonify({"error": "Could not find image count."}), 400

        match = re.search(r'\b\d+\b', h1.text)
        if not match:
            return jsonify({"error": "Could not extract image count."}), 400

        image_count = int(match.group())
        downloaded = 0
        failed = 0

        for i in range(1, image_count + 1):
            img_url = f"{base_url}{i}.webp"
            img_data = requests.get(img_url)
            if img_data.status_code == 200:
                file_path = os.path.join(save_path, f"{folder_name} {i:03d}.jpg")
                with open(file_path, 'wb') as f:
                    f.write(img_data.content)
                downloaded += 1
            else:
                failed += 1

        return jsonify({
            "success": True,
            "downloaded": downloaded,
            "failed": failed,
            "folder": folder_name
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    os.makedirs("downloads", exist_ok=True)
    app.run(debug=True)
