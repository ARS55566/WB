import os
import re
import requests
import time
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import zipfile
import io

app = Flask(__name__)
CORS(app)

@app.route('/')
def serve_index():
    return send_file('index.html')

@app.route('/download', methods=['POST'])
def download_images():
    try:
        data = request.get_json(force=True)
        url = data.get('url')
        total = int(data.get('total'))
        batch_size = int(data.get('batch_size'))

        if not url or total <= 0 or batch_size <= 0:
            return jsonify({"success": False, "error": "Invalid input values."}), 400

        headers = {'User-Agent': 'Mozilla/5.0'}
        html = requests.get(url, headers=headers, timeout=20).text
        soup = BeautifulSoup(html, 'html.parser')

        name_parts = [a.text.strip() for div in soup.find_all('div', class_='pb-2')
                      for a in div.find_all('a') if a.text.strip()]
        folder_name = " - ".join(name_parts).replace(":", "").replace("/", " ")
        if not folder_name:
            folder_name = "ImageGallery_" + str(int(time.time()))

        save_path = os.path.join("downloads", folder_name)
        os.makedirs(save_path, exist_ok=True)

        sample_img = soup.find('a', href=re.compile(r'/images/.*\.(webp|jpg|jpeg|png)'))
        if not sample_img:
            return jsonify({"success": False, "error": "Could not find sample image URL."}), 400

        sample_url = sample_img['href']
        if not sample_url.startswith('http'):
            sample_url = 'https://waifubitches.com' + sample_url

        base_match = re.match(r"(https://.*/)(\d+)\.(webp|jpg|jpeg|png)", sample_url)
        if not base_match:
            return jsonify({"success": False, "error": "Could not extract base URL."}), 400

        base_url = base_match.group(1)
        start_number = int(base_match.group(2))
        extension = base_match.group(3)

        downloaded = 0
        failed = 0
        image_urls = []

        current = 0
        while current < total:
            end = min(current + batch_size, total)
            for i in range(current, end):
                img_id = start_number + i
                img_url = f"{base_url}{img_id}.{extension}"
                try:
                    img_data = requests.get(img_url, headers=headers, timeout=5)
                    if img_data.status_code == 200:
                        filename = f"{folder_name} {img_id:03d}.{extension}"
                        file_path = os.path.join(save_path, filename)
                        if not os.path.exists(file_path):
                            with open(file_path, 'wb') as f:
                                f.write(img_data.content)
                        image_urls.append(f"/downloads/{folder_name}/{filename}")
                        downloaded += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"Error fetching {img_url}: {e}")
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
                "zip_url": f"/download_zip/{zip_filename}",
                "thumbnails": image_urls
            })

            current += batch_size

    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/downloads/<folder>/<filename>')
def serve_image(folder, filename):
    return send_from_directory(os.path.join("downloads", folder), filename)

@app.route('/download_zip/<filename>')
def serve_zip(filename):
    return send_from_directory('downloads', filename, as_attachment=True)

if __name__ == '__main__':
    os.makedirs("downloads", exist_ok=True)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
