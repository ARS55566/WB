import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import zipfile
import io
import logging # Import the logging module

# Configure logging for the Flask application
# Set the logging level to INFO for general messages, or DEBUG for more detailed output.
# Logs will be printed to the console/standard output, which Render captures.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app) # Enable Cross-Origin Resource Sharing for the Flask app

# Route to serve the main HTML file (your frontend)
@app.route('/')
def serve_index():
    """
    Serves the index.html file when the root URL is accessed.
    """
    # Assuming index.html is in the same directory as app.py
    return send_file('index.html')

# Route to handle image download requests
@app.route('/download', methods=['POST'])
def download_images():
    """
    Handles POST requests to download images from a specified URL within a given range.
    It scrapes image URLs, downloads them, and zips them for download.
    """
    try:
        # Parse JSON data from the request body
        data = request.get_json(force=True)
        url = data.get('url')
        range_str = data.get('range')

        # Validate input parameters
        if not url or not range_str or not re.match(r'^\d+\s*-\s*\d+$', range_str):
            app.logger.error("Invalid URL or range format received. URL: %s, Range: %s", url, range_str)
            return jsonify({"success": False, "error": "Invalid URL or range. Use format 1-20"}), 400

        # Extract start and end numbers from the range string
        start, end = map(int, re.findall(r'\d+', range_str))
        if start > end:
            app.logger.error("Invalid range: start (%d) must be <= end (%d).", start, end)
            return jsonify({"success": False, "error": "Start must be <= end."}), 400

        # Define headers for the HTTP request to mimic a browser
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}
        
        app.logger.info("Attempting to fetch HTML from URL: %s", url)
        
        # Fetch the HTML content of the gallery page
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        html = response.text

        # --- CRITICAL DEBUGGING LOG ---
        # Log the first 2000 characters of the received HTML for debugging purposes.
        # This helps in identifying if the server is receiving the expected HTML content
        # or a blocked/different page.
        app.logger.debug("Received HTML (first 2000 chars):\n%s", html[:2000])
        app.logger.info("HTTP Status Code for %s: %d", url, response.status_code)
        # ------------------------------

        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Attempt to extract folder name from specific div/a tags
        # This part is highly dependent on the target website's HTML structure
        name_parts = [a.text.strip() for div in soup.find_all('div', class_='pb-2')
                      for a in div.find_all('a') if a.text.strip()]
        folder_name = " - ".join(name_parts).replace(":", "").replace("/", " ").strip()
        if not folder_name:
            folder_name = "ImageGallery" # Default folder name if extraction fails

        # Create a directory to save downloaded images
        save_path = os.path.join("downloads", folder_name)
        os.makedirs(save_path, exist_ok=True) # Create if it doesn't exist

        # Find a sample image URL to determine the base URL pattern
        # This regex looks for an 'a' tag with an href containing '/images/' and ending in '.webp'
        sample_img = soup.find('a', href=re.compile(r'/images/.*\.webp'))
        if not sample_img:
            app.logger.error("Failed to find sample image URL for %s. The HTML structure might have changed or the URL pattern is different.", url)
            # You can log the full HTML here if app.logger.level is DEBUG
            # app.logger.debug("Full HTML content that failed to find sample_img:\n%s", html)
            return jsonify({"success": False, "error": "Could not find sample image URL. The website's structure might have changed."}), 400

        sample_url = sample_img['href']
        # Prepend base domain if the URL is relative
        if not sample_url.startswith('http'):
            # This assumes the base domain is hardcoded, which might need adjustment
            # based on the actual domain of the gallery URL provided by the user.
            # A more robust solution would parse the domain from the 'url' variable.
            sample_url = 'https://waifubitches.com' + sample_url

        # Extract the base URL and the starting image number from the sample URL
        base_match = re.match(r"(https://.*/)\d+\.webp", sample_url)
        if not base_match:
            app.logger.error("Could not extract base URL from sample_url: %s", sample_url)
            return jsonify({"success": False, "error": "Could not extract base URL from sample image URL."}), 400

        base_url = base_match.group(1)
        match = re.search(r"/(\d+)\.webp$", sample_url)
        # The 'number' here is the numerical part of the first image found.
        # It's used to adjust the range for downloading subsequent images.
        number = int(match.group(1)) if match else 0

        downloaded = 0
        failed = 0
        image_urls = [] # To store URLs of downloaded images for frontend display

        # Loop through the specified range to download images
        for img_id in range(start + number - 1, end + number):
            img_url = f"{base_url}{img_id}.webp"
            try:
                app.logger.info("Downloading image: %s", img_url)
                img_data = requests.get(img_url, headers=headers, timeout=10) # Increased timeout slightly
                if img_data.status_code == 200:
                    filename = f"{folder_name} {img_id:03d}.webp" # Format filename with leading zeros
                    file_path = os.path.join(save_path, filename)
                    with open(file_path, 'wb') as f:
                        f.write(img_data.content)
                    image_urls.append(f"/downloads/{folder_name}/{filename}")
                    downloaded += 1
                    app.logger.info("Successfully downloaded: %s", filename)
                else:
                    failed += 1
                    app.logger.warning("Failed to download %s. Status code: %d", img_url, img_data.status_code)
            except requests.exceptions.RequestException as img_req_err:
                failed += 1
                app.logger.error("Error downloading %s: %s", img_url, img_req_err)
            except Exception as e:
                failed += 1
                app.logger.error("Unexpected error during image download for %s: %s", img_url, e)

        # Create a ZIP archive of all downloaded images
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(save_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # arcname is the name of the file inside the zip (relative path)
                    arcname = os.path.relpath(file_path, save_path)
                    zipf.write(file_path, arcname)
        zip_buffer.seek(0) # Rewind the buffer to the beginning

        zip_filename = f"{folder_name}.zip"
        # Save the zip file to the 'downloads' directory
        zip_path = os.path.join("downloads", zip_filename)
        with open(zip_path, "wb") as f:
            f.write(zip_buffer.read())

        app.logger.info("Download process complete. Downloaded: %d, Failed: %d. Zip created: %s", downloaded, failed, zip_filename)
        return jsonify({
            "success": True,
            "downloaded": downloaded,
            "failed": failed,
            "folder": folder_name,
            "zip_url": f"/download_zip/{zip_filename}",
            "thumbnails": image_urls
        })

    except requests.exceptions.RequestException as req_err:
        # Catch network-related errors during the initial HTML fetch
        app.logger.error("Network request error during initial HTML fetch for URL %s: %s", url, req_err, exc_info=True)
        return jsonify({"success": False, "error": f"Network request error: {req_err}. The target website might be blocking access or the URL is incorrect."}), 500
    except Exception as e:
        # Catch any other unexpected errors
        app.logger.critical("An unexpected error occurred in download_images: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

# Route to serve individual downloaded images (for thumbnails)
@app.route('/downloads/<folder>/<filename>')
def serve_image(folder, filename):
    """
    Serves individual image files from the 'downloads' directory.
    """
    app.logger.info("Serving image: %s/%s", folder, filename)
    return send_from_directory(os.path.join("downloads", folder), filename)

# Route to serve the generated ZIP file
@app.route('/download_zip/<filename>')
def serve_zip(filename):
    """
    Serves the generated ZIP file for download.
    """
    app.logger.info("Serving ZIP file: %s", filename)
    return send_from_directory('downloads', filename, as_attachment=True)

# Main entry point for the Flask application
if __name__ == '__main__':
    # Ensure the 'downloads' directory exists when the app starts
    os.makedirs("downloads", exist_ok=True)
    app.logger.info("Starting Flask application. 'downloads' directory ensured.")
    # Run the Flask app
    # host='0.0.0.0' makes the server accessible from any IP,
    # port is taken from environment variable (e.g., set by Render) or defaults to 5000.
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

