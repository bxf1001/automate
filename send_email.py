import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import openpyxl
from email.mime.base import MIMEBase
from email import encoders
import mimetypes
import os
def get_attachment_files(folder_path='attachments'):
    return [os.path.join(folder_path, f) for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]

def load_email_content_from_excel(filename):
    wb = openpyxl.load_workbook(filename)
    sheet = wb.active
    subject = sheet['A2'].value
    body = sheet['A9'].value
    return subject, body
def load_emails_from_csv(filename):
    emails = []
    with open(filename, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Emails']:
                emails.extend(row['Emails'].split(', '))
    return list(set(emails))  # Remove duplicates
def get_mime_type(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        return 'application/octet-stream'
    return mime_type
def send_emails(email_list, subject, body):
    sender_email = "srisuryaharadevindustries@gmail.com"
    #sender_password = "lozq djfa dduh mxyj"  #max
    sender_password = "ugam bejh xlpw zics"  #srisurya

    attachment_files = get_attachment_files()

    for recipient in email_list:
        message = MIMEMultipart()
        message['From'] = sender_email
        message['To'] = recipient
        message['Subject'] = subject
        message.attach(MIMEText(body, 'plain'))

        for file_path in attachment_files:
            mime_type = get_mime_type(file_path)
            with open(file_path, "rb") as file:
                part = MIMEBase(*mime_type.split('/'))
                part.set_payload(file.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(file_path)}"')
            message.attach(part)

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(message)

    print(f"Emails sent to {len(email_list)} recipients with {len(attachment_files)} attachments.")


# In the main section:
if __name__ == "__main__":
    csv_filename = "feed_factories_emails.csv"
    excel_filename = "email_content.xlsx"
    
    email_list = load_emails_from_csv(csv_filename)
    subject, body = load_email_content_from_excel(excel_filename)
    send_emails(email_list, subject, body)