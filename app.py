import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory
from urllib.parse import urlparse
from flask_cors import CORS
import zipfile
import io

app = Flask(__name__, static_folder='static')
CORS(app)

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/download', methods=['POST'])
def download_images():
    import zipfile
    import io

    data = request.get_json()
    url = data.get('url')

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        html = requests.get(url, headers=headers).text
        soup = BeautifulSoup(html, 'html.parser')

        # Extract folder name
        name_parts = [a.text.strip() for div in soup.find_all('div', class_='pb-2') for a in div.find_all('a') if a.text.strip()]
        folder_name = " - ".join(name_parts).replace(":", "").replace("/", " ")
        if not folder_name:
            folder_name = "ImageGallery"

        save_path = os.path.join("downloads", folder_name)
        os.makedirs(save_path, exist_ok=True)

        # Base image URL
        photo_div = soup.find('div', class_='d-flex justify-content-center photo-item')
        if not photo_div:
            return jsonify({"success": False, "error": "Could not find image preview link."}), 400

        href = photo_div.find('a')['href']
        base_url = href.rsplit('/', 1)[0] + '/'

        # Image count
        h1 = soup.find('h1', class_='container text-center text-uppercase h6 mt-2')
        if not h1:
            return jsonify({"success": False, "error": "Could not find image count."}), 400

        match = re.search(r'\b\d+\b', h1.text)
        if not match:
            return jsonify({"success": False, "error": "Could not extract image count."}), 400

        image_count = int(match.group())
        downloaded = 0
        failed = 0

        for i in range(1, image_count + 1):
            img_url = f"{base_url}{i}.webp"
            img_data = requests.get(img_url, headers=headers)
            if img_data.status_code == 200:
                file_path = os.path.join(save_path, f"{folder_name} {i:03d}.jpg")
                with open(file_path, 'wb') as f:
                    f.write(img_data.content)
                downloaded += 1
            else:
                failed += 1

        # Zip the folder
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(save_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, save_path)
                    zipf.write(file_path, arcname)

        zip_buffer.seek(0)
        zip_filename = f"{folder_name}.zip"
        zip_path = os.path.join("downloads", zip_filename)
        with open(zip_path, "wb") as f:
            f.write(zip_buffer.read())

        return jsonify({
            "success": True,
            "downloaded": downloaded,
            "failed": failed,
            "folder": folder_name,
            "zip_url": f"/download_zip/{zip_filename}"
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/download_zip/<filename>')
def serve_zip(filename):
    return send_from_directory('downloads', filename, as_attachment=True)

if __name__ == '__main__':
    os.makedirs("downloads", exist_ok=True)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
