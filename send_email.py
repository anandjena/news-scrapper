import smtplib
import os
from email.message import EmailMessage
import datetime

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today_ist = datetime.datetime.now(IST).date()
FILENAME = f"news_{today_ist.isoformat()}.csv"

def send_email_with_attachment():
    msg = EmailMessage()
    msg["Subject"] = f"News Scraper Report - {today_ist}"
    msg["From"] = os.environ["EMAIL_USER"]
    msg["To"] = os.environ["RECIPIENT_EMAIL"]
    msg.set_content("Attached is the latest news CSV file from the scraper.")

    with open(FILENAME, "rb") as f:
        msg.add_attachment(f.read(), maintype="text", subtype="csv", filename=FILENAME)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
        smtp.send_message(msg)

if __name__ == "__main__":
    send_email_with_attachment()
    print("✅ Email sent successfully!")
