from dotenv import load_dotenv
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

load_dotenv()

account_sid = os.getenv('TWILIO_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'

app = Flask(__name__)

def authenticate_google_drive():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            http = httplib2.Http()
            creds.refresh(Request(http))
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, folder_name):
    # Buscar la carpeta por nombre
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    
    if items:
        # Si la carpeta existe, devolver su ID
        return items[0]['id']
    else:
        # Si la carpeta no existe, crearla
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def upload_to_google_drive(file_name):
    service = authenticate_google_drive()

    folder_id = get_or_create_folder(service, 'bot whatsapp')
    
    mime_type = 'image/jpeg'  
    
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]  # Especificamos la carpeta de destino
    }
    media = MediaFileUpload(file_name, mimetype=mime_type)  # Subimos el archivo como JPG
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    if file.get('id'):
        print(f"Archivo subido con éxito a Google Drive con ID: {file.get('id')}")

@app.route("/whatsapp-webhook", methods=['POST'])
def whatsapp_webhook():
    media_url = request.form.get('MediaUrl0')  # URL de la imagen
    if media_url:
        unique_file_name = generate_unique_filename()  # Generar nombre único para la imagen
        download_media(media_url, unique_file_name)  # Descargar la imagen
        process_and_upload_image(unique_file_name)  # Procesar la imagen y subirla al drive
    return "OK"

def generate_unique_filename():
    unique_name = str(uuid.uuid4()) + ".jpeg"  
    return unique_name

def download_media(media_url, file_name):
    try:
        processed_folder = 'processed_images'
        if not os.path.exists(processed_folder):
            os.makedirs(processed_folder)
        file_path = os.path.join(processed_folder, file_name)
        
        response = requests.get(media_url, auth=(account_sid, auth_token))
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                f.write(response.content)
            print(f"Imagen descargada con éxito: {file_path}")
        else:
            raise Exception(f"Error al descargar la imagen: {response.status_code}, URL: {media_url}")
    except Exception as e:
        print(f"Error al descargar la imagen: {e}")

def process_and_upload_image(file_name):
    try:
        processed_folder = 'processed_images'
        file_path = os.path.join(processed_folder, file_name)
        
        # Verificar que el archivo descargado sea un archivo de imagen válido
        with open(file_path, 'rb') as f:
            if not f.read(10):
                raise ValueError("El archivo descargado está vacío o no es válido")

        # Abrir la imagen con PIL
        with Image.open(file_path) as img:
            # Convertirla a JPG si no lo es
            if img.format != 'JPEG':
                img = img.convert('RGB')
            
            # Guardar la imagen como JPG
            img.save(file_path, 'JPEG')

        # Verificar que el archivo guardado sea un JPEG válido
        with Image.open(file_path) as img:
            if img.format != 'JPEG':
                raise ValueError("El archivo no se guardó como JPEG correctamente")

        # Subir la imagen al Google Drive
        upload_to_google_drive(file_path)

    except Exception as e:
        print(f"Error al procesar la imagen: {e}")

if __name__ == "__main__":
    app.run(debug=True)