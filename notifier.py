import smtplib
import os
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def send_email(subject, body):
    sender_email = os.getenv("EMAIL_SENDER")
    receiver_email = os.getenv("EMAIL_RECEIVER")
    password = os.getenv("EMAIL_PASSWORD")

    missing = []
    if not sender_email: missing.append("EMAIL_SENDER")
    if not receiver_email: missing.append("EMAIL_RECEIVER")
    if not password: missing.append("EMAIL_PASSWORD")

    if missing:
        print(f"Skipped email notification. Missing variables: {', '.join(missing)}")
        return

    # Create message
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    try:
        # Connect to Gmail SMTP server
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        # print(f"✅ Email sent: {subject}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def send_telegram(message):
    """Send message via Telegram Bot API (Fallback for cloud SMTP blocking)"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        return # Telegram not configured

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if not response.ok:
            print(f"❌ Telegram Error: {response.text}")
    except Exception as e:
        print(f"❌ Telegram Connection Error: {e}")

def notify(subject, body):
    """Notify via both Email and Telegram if configured"""
    # Try Email
    send_email(subject, body)
    
    # Try Telegram
    full_message = f"🔔 {subject}\n\n{body}"
    send_telegram(full_message)

if __name__ == "__main__":
    # Test notification
    send_email("🚀 Bot Test", "This is a test notification from your Trading Bot!")
