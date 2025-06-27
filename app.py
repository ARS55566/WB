import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory
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
    data = request.get_json()
    url = data.get('url')

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        html = requests.get(url, headers=headers).text
        soup = BeautifulSoup(html, 'html.parser')

        # Extract folder name
        name_parts = [a.text.strip() for div in soup.find_all('div', class_='pb-2') for a in div.find_all('a') if
                      a.text.strip()]
        folder_name = " - ".join(name_parts).replace(":", "").replace("/", " ")
        if not folder_name:
            folder_name = "ImageGallery"

        save_path = os.path.join("downloads", folder_name)
        os.makedirs(save_path, exist_ok=True)

        # Get image count from <h1 class="h6">
        h1 = soup.find('h1', class_='h6')
        if not h1:
            return jsonify({"success": False, "error": "Could not find image count."}), 400

        match = re.search(r'\d+', h1.text)
        if not match:
            return jsonify({"success": False, "error": "Could not extract image count."}), 400

        image_count = int(match.group())

        # Find the first image URL to get base + start ID
        first_img_tag = soup.find('a', href=re.compile(r'/images/.+\.webp'))
        if not first_img_tag:
            return jsonify({"success": False, "error": "Could not find initial image URL."}), 400

        first_img_url = first_img_tag['href']
        if not first_img_url.startswith('http'):
            first_img_url = 'https://waifubitches.com' + first_img_url

        img_match = re.match(r"(https://.*/)(\d+)\.webp", first_img_url)
        if not img_match:
            return jsonify({"success": False, "error": "Could not parse image URL pattern."}), 400

        base_url, start_id_str = img_match.groups()
        start_id = int(start_id_str)

        # Download images in sequence
        downloaded = 0
        failed = 0
        for i in range(image_count):
            img_id = start_id + i
            img_url = f"{base_url}{img_id}.webp"

            try:
                img_data = requests.get(img_url, headers=headers, timeout=10)
                if img_data.status_code == 200:
                    file_path = os.path.join(save_path, f"{folder_name} {i + 1:03d}.webp")
                    with open(file_path, 'wb') as f:
                        f.write(img_data.content)
                    downloaded += 1
                else:
                    failed += 1
                    break  # or continue to skip
            except Exception as e:
                print(f"Error fetching {img_url}: {e}")
                failed += 1
                break  # or continue to skip

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
