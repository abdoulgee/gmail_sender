import csv
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
from pyppeteer import connect
import threading
import io
import base64
import hashlib
from cryptography.fernet import Fernet
import os  # Add this at the top
from threading import Lock

os.environ['PYPPETEER_SKIP_DOWNLOAD'] = 'true'
# Change secret key line to:
secret_key = os.getenv("SECRET_KEY", "50001")  # Default for testing

app = Flask(__name__)
# Remove supports_credentials=True
CORS(app, resources={r"/*": {"origins": "*"}})




# In app.py
from urllib.parse import urlparse

def is_valid_ws_url(url):
    try:
        result = urlparse(url)
        return all([
            result.scheme in ['ws', 'wss'],
            #result.hostname in ['localhost', '127.0.0.1'],
            result.port in range(9222, 9333)  # Common debug ports
        ])
    except:
        return False

# Generate the key from the secret passphrase
#secret_key = "50001"
key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())

cipher = Fernet(key)

# Read the encrypted file
with open("emails_encrypted.csv", "rb") as file:
    encrypted_data = file.read()

# Decrypt the data
decrypted_data = cipher.decrypt(encrypted_data).decode()

# Convert decrypted data into a CSV-like variable
csv_file = io.StringIO(decrypted_data)
csv_reader = csv.reader(csv_file)

# Store as a list of rows
decrypted_csv = [row for row in csv_reader]

# Global variables to track email sending

delay_seconds = 0
stop_event = threading.Event()
current_browser = None
# Add these after global variables
sent_count_lock = Lock()
email_limit_lock = Lock()

# Simulate human-like typing
async def simulate_human_typing(element, text):
    await element.click()
    for char in text:
        await element.type(char)
        await asyncio.sleep(random.uniform(0.1, 0.15))

async def slow_scroll_container(page, scroll_container, scroll_amount, duration):
    await page.evaluate('''(element, scrollAmount, duration) => {
        const start = element.scrollTop;
        const startTime = performance.now();

        const scroll = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            element.scrollTop = start + (scrollAmount * progress);

            if (progress < 1) {
                requestAnimationFrame(scroll);
            }
        };

        requestAnimationFrame(scroll);
    }''', scroll_container, scroll_amount, duration)

async def scroll_down_and_up(page, scroll_container, scroll_amount, duration):
    # Scroll down
    await slow_scroll_container(page, scroll_container, scroll_amount, duration)
    await asyncio.sleep(1)
    # Scroll back up
    await slow_scroll_container(page, scroll_container, -scroll_amount, duration)

async def send_single_email(page, email, subjectlines, messagebodys):
    try:
        # Select random subject and message
        subject_options = [s.strip() for s in subjectlines.split(',,')]
        message_options = [m.strip() for m in messagebodys.split(',,')]
        subject = random.choice(subject_options).replace('{{first_name}}', email['first_name'])
        message = random.choice(message_options).replace('{{first_name}}', email['first_name'])

        # Scroll down and up
        scroll_container = await page.waitForXPath("//DIV[@id=':3']", timeout=10000)
        if scroll_container:
            await scroll_down_and_up(page, scroll_container, scroll_amount=1000, duration=1000)
        else:
            print("Scroll container not found!")
        
        await asyncio.sleep(3)

        # Click the Compose button
        compose_button = await page.waitForXPath(
            "//DIV[@class='T-I T-I-KE L3'][text()='Compose']/self::DIV",
            timeout=10000
        )
        await compose_button.click()
        await asyncio.sleep(2)

        # Fill recipient email
        to_field = await page.waitForSelector("input[aria-label='To recipients']", timeout=10000)
        await simulate_human_typing(to_field, email['email'])

        # Fill subject
        subject_field = await page.waitForSelector("input[name='subjectbox']", timeout=10000)
        await simulate_human_typing(subject_field, subject)

        # Fill message body
        message_div = await page.waitForSelector("div[aria-label='Message Body']", timeout=10000)
        await simulate_human_typing(message_div, message)

        # Click Send button
        send_button = await page.waitForSelector("div[aria-label='Send ‪(Ctrl-Enter)‬']", timeout=10000)
        await send_button.click()

        # Wait for compose window to close
        await page.waitForSelector("div[role='dialog']", hidden=True, timeout=20000)
        await asyncio.sleep(2)
        
        print(f"Sent email to {email['email']}")
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

def get_next_email():
    """Read the next valid email from emails.csv without loading all into memory."""
    try:
        #with open(decrypted_csv, 'r') as f:
          #  reader = csv.reader(f, delimiter=',')
        for row in decrypted_csv:
            if len(row) >= 2:
                return {
                    'email': row[0].strip(),
                    'first_name': row[1].strip()
                }
    except Exception as e:
        print(f"Error reading email: {str(e)}")
    return None

def remove_sent_email(email_to_remove):
    """Remove a single sent email from decrypted_csv (in-memory list) and update the encrypted file."""
    global decrypted_csv
    try:
        # Remove the email from the in-memory list
        decrypted_csv = [row for row in decrypted_csv if len(row) < 1 or row[0].strip() != email_to_remove['email'].strip()]

        # Encrypt the updated list and write back to emails_encrypted.csv
        updated_csv_content = io.StringIO()
        csv_writer = csv.writer(updated_csv_content)
        csv_writer.writerows(decrypted_csv)
        
        encrypted_data = cipher.encrypt(updated_csv_content.getvalue().encode())

        with open("emails_encrypted.csv", "wb") as file:
            file.write(encrypted_data)

        print(f"Removed and updated email: {email_to_remove['email']}")
    except Exception as e:
        print(f"Error removing email: {str(e)}")



async def open_and_click(ws_url, url, subjectlines, messagebodys, email_limit, delay_seconds):
    global sent_count, current_page, current_browser, stop_flag
    print(f"Connecting to browser at: {ws_url}")  # <-- ADD
    
    try:
        current_browser = await connect(browserWSEndpoint=ws_url, defaultViewport=None, ignoreHTTPSErrors=True)
        print("Browser connected!")  # <-- ADD
        current_page = await current_browser.newPage()
        print("New page created!")  # <-- ADD

        await current_page.goto(url, timeout=60000)
        print(f"Navigated to: {url}")  # <-- ADD
        # ... rest of the function ...
        with sent_count_lock:
            sent_count = 0

        while sent_count < email_limit and not stop_flag:
            email = get_next_email()

            if not email:
                print("No more emails to send.")
                break

            try:
                success = await send_single_email(current_page, email, subjectlines, messagebodys)
                if success:
                    with sent_count_lock:
                        sent_count += 1
                        remove_sent_email(email)  # Ensure it's removed immediately after sending
                        print(f"Total emails sent: {sent_count}")

                    if delay_seconds > 0 and not stop_flag:
                        print(f"Waiting {delay_seconds} seconds before next email...")
                        await asyncio.sleep(delay_seconds)
                else:
                    print("Failed to send email, will retry next iteration.")
            except Exception as e:
                print(f"Error in email sending loop: {str(e)}")
                continue

        return {"message": f"Process stopped. Sent {sent_count} emails"} if stop_flag else {"message": f"Successfully sent {sent_count} emails"}
    except Exception as e:
        return {"error": f"Operation failed: {str(e)}"}
    finally:
        # Disconnect without closing the browser
        await current_page.close()
        await current_browser.disconnect()
        current_page = None
        current_browser = None


@app.route('/get-sent-count', methods=['GET'])
def get_sent_count():
    with sent_count_lock, email_limit_lock:
        return jsonify({
            "sentCount": sent_count,
            "totalCount": email_limit
        })

sending_thread = None

@app.route('/click-compose', methods=['POST'])
def click_compose():
    global sending_thread, email_limit, delay_seconds, stop_flag

    # Get data from request first
    with email_limit_lock:
        email_limit = int(data.get('emailLimit', 0))
    data = request.json
    ws_url = data.get("wsUrl")  # Retrieve ws_url here
    url = data.get("url")
    subjectlines = data.get('subjectlines')
    messagebodys = data.get('messagebodys')
    delay_seconds = int(data.get('delaySeconds', 0)) * 60

    # Validate required fields
    if not ws_url:
        return jsonify({"error": "WebSocket URL is required"}), 400
    if not url:
        return jsonify({"error": "Gmail URL is required"}), 400
    if not subjectlines or not messagebodys or email_limit <= 0:
        return jsonify({"error": "Subject lines, message bodies, and valid email limit are required"}), 400

    # Validate WebSocket URL format
    from urllib.parse import urlparse
    try:
        parsed = urlparse(ws_url)
        if not parsed.scheme.startswith('ws'):
            return jsonify({"error": "Invalid WebSocket URL scheme"}), 400
    except Exception as e:
        return jsonify({"error": f"Invalid URL format: {str(e)}"}), 400

    # Check if already running
    if sending_thread and sending_thread.is_alive():
        return jsonify({"message": "Email sending is already running"}), 400

    stop_flag = False  # Reset flag
    print(f"Starting with WS URL: {ws_url}")

    # Start thread with correct argument order
    sending_thread = threading.Thread(
        target=run_email_sending,
        args=(ws_url, url, subjectlines, messagebodys, email_limit, delay_seconds)
    )
    sending_thread.start()
    return jsonify({"message": "Email sending started in the background"})


# Replace run_email_sending function with:
def run_email_sending(ws_url, url, subjectlines, messagebodys, email_limit, delay_seconds):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            open_and_click(ws_url, url, subjectlines, messagebodys, email_limit, delay_seconds)
        )
    except Exception as e:
        print(f"Critical error: {str(e)}")
    finally:
        loop.close()

# Add this endpoint
@app.route('/stop', methods=['POST'])
def stop_sending():
    global stop_flag
    stop_flag = True
    return jsonify({
        "message": "Stopping process after current email...",
        "sentCount": sent_count,
        "totalCount": email_limit
    })

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)

