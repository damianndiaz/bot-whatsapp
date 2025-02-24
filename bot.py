import uuid
import os
import requests
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from google_auth_oauthlib.flow import InstalledAppFlow
from google_auth_httplib2 import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from mimetypes import guess_type
from PIL import Image
import io
import httplib2
import shutil

# Obtener credenciales de Twilio desde GitHub Secrets
account_sid = os.getenv('TWILIO_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

# Obtener credenciales de Google Drive desde GitHub Secrets
credentials_json = os.getenv('CREDENTIALS')
token_json = os.getenv('TOKEN')

SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Configuración de Flask
app = Flask(__name__)

# Función para autenticar con Google Drive
def authenticate_google_drive():
    creds = None
    if token_json:
        creds = Credentials.from_authorized_user_info(eval(token_json), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            http = httplib2.Http()
            creds.refresh(Request(http))
        else:
            flow = InstalledAppFlow.from_client_config(eval(credentials_json), SCOPES)
            creds = flow.run_local_server(port=0)
    return build('drive', 'v3', credentials=creds)

# Función para obtener o crear la carpeta en Google Drive
def get_or_create_folder(service, folder_name):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    
    if items:
        return items[0]['id']
    else:
        file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

# Función para subir la imagen a Google Drive
def upload_to_google_drive(file_path):
    service = authenticate_google_drive()
    folder_id = get_or_create_folder(service, 'bot whatsapp')
    mime_type = 'image/jpeg'
    file_name = os.path.basename(file_path)
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype=mime_type)
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id') is not None

@app.route("/whatsapp-webhook", methods=['POST'])
def whatsapp_webhook():
    media_url = request.form.get('MediaUrl0')
    sender = request.form.get('From')
    resp = MessagingResponse()
    
    if media_url:
        unique_file_name = generate_unique_filename()
        processed_folder = 'processed_images'
        os.makedirs(processed_folder, exist_ok=True)
        file_path = os.path.join(processed_folder, unique_file_name)
        
        if download_media(media_url, file_path):
            if process_and_upload_image(file_path):
                resp.message("La imagen se subió correctamente a Google Drive.")
                os.remove(file_path)
            else:
                resp.message("Hubo un error al subir la imagen a Google Drive.")
        else:
            resp.message("Hubo un error al descargar la imagen.")
    else:
        resp.message("No se recibió ninguna imagen.")
    
    return str(resp)

# Función para generar nombres únicos de archivo
def generate_unique_filename():
    return str(uuid.uuid4()) + ".jpeg"

# Función para descargar la imagen
def download_media(media_url, file_path):
    headers = {"Accept": "image/*"}
    response = requests.get(media_url, auth=(account_sid, auth_token), headers=headers)
    if response.status_code == 200:
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return True
    return False

# Procesar la imagen y subirla
def process_and_upload_image(file_path):
    try:
        with Image.open(file_path) as img:
            if img.format != 'JPEG':
                img = img.convert('RGB')
            img.save(file_path, 'JPEG')
        return upload_to_google_drive(file_path)
    except Exception as e:
        print(f"Error al procesar la imagen: {e}")
        return False

@app.route("/send-whatsapp-message", methods=['GET'])
def send_whatsapp_message():
    message = client.messages.create(
        body="Hola, esta es una prueba de Twilio",
        from_='whatsapp:+12187893490',
        to='whatsapp:+5491132662924'
    )
    return f"Mensaje enviado con SID: {message.sid}"

if __name__ == "__main__":
    app.run(debug=True)
