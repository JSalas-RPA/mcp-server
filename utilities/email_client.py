import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

# Configuración del servidor SMTP y credenciales
smtp_server = os.getenv("SMTP_SERVER")
port = int(os.getenv("SMTP_PORT", 587))
user = os.getenv("SMTP_USER")
password = os.getenv("SMTP_PASSWORD")
sender = os.getenv("EMAIL_FROM")
recipient = os.getenv("ADMIN_EMAIL")

def send_email(error):
        try:
            print("Enviando email de notificación de error...")
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = recipient
            msg['Subject'] = "Notificación de Error en el Sistema"

            msg.attach(MIMEText(error, 'plain'))

            with smtplib.SMTP(smtp_server, port) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            return True, "Email enviado con éxito"
        except Exception as e:
            print(f"Error enviando email: {str(e)}")
            return False, f"Error enviando email: {str(e)}"
        

    