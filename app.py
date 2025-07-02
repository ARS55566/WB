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

        root_path = os.path.join("downloads", folder_name)
        os.makedirs(root_path, exist_ok=True)

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
        zip_urls = []

        current = 0
        batch_num = 1

        while current < total:
            end = min(current + batch_size, total)
            batch_folder = os.path.join(root_path, f"Batch_{batch_num}")
            os.makedirs(batch_folder, exist_ok=True)

            for i in range(current, end):
                img_id = start_number + i
                img_url = f"{base_url}{img_id}.{extension}"
                try:
                    img_data = requests.get(img_url, headers=headers, timeout=5)
                    if img_data.status_code == 200:
                        filename = f"{folder_name} {img_id:03d}.{extension}"
                        file_path = os.path.join(batch_folder, filename)
                        if not os.path.exists(file_path):
                            with open(file_path, 'wb') as f:
                                f.write(img_data.content)
                        image_urls.append(f"/downloads/{folder_name}/Batch_{batch_num}/{filename}")
                        downloaded += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"Error fetching {img_url}: {e}")
                    failed += 1

            # Create ZIP for this batch
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(batch_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, batch_folder)
                        zipf.write(file_path, arcname)

            zip_buffer.seek(0)
            zip_filename = f"{folder_name}_Batch_{batch_num}.zip"
            zip_path = os.path.join("downloads", zip_filename)
            with open(zip_path, "wb") as f:
                f.write(zip_buffer.read())
            zip_urls.append(f"/download_zip/{zip_filename}")

            current += batch_size
            batch_num += 1

        return jsonify({
            "success": True,
            "downloaded": downloaded,
            "failed": failed,
            "folder": folder_name,
            "zip_urls": zip_urls,
            "thumbnails": image_urls
        })

    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
