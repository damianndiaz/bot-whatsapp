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

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# Obtener las credenciales de Twilio de las variables de entorno
account_sid = os.getenv('TWILIO_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
print(f"Twilio SID: {account_sid}")
print(f"Twilio Auth Token: {auth_token}")
client = Client(account_sid, auth_token)

# Configuración de Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'

# Configuración de Flask
app = Flask(__name__)

# Función para autenticar con Google Drive
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

# Función para obtener o crear la carpeta "bot whatsapp" en Google Drive
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

# Función para subir la foto a Google Drive
def upload_to_google_drive(file_path):
    service = authenticate_google_drive()
    folder_id = get_or_create_folder(service, 'bot whatsapp')
    
    mime_type = 'image/jpeg'  # Forzamos JPG
    file_name = os.path.basename(file_path)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype=mime_type)
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    if file.get('id'):
        print(f"Archivo subido con éxito a Google Drive con ID: {file.get('id')}")
        return True
    return False

@app.route("/whatsapp-webhook", methods=['POST'])
def whatsapp_webhook():
    media_url = request.form.get('MediaUrl0')
    sender = request.form.get('From')
    
    resp = MessagingResponse()
    
    if media_url:
        unique_file_name = generate_unique_filename()
        processed_folder = 'processed_images'
        if not os.path.exists(processed_folder):
            os.makedirs(processed_folder)
        file_path = os.path.join(processed_folder, unique_file_name)
        
        download_success = download_media(media_url, file_path)
        if download_success:
            success = process_and_upload_image(file_path)
            if success:
                resp.message("La imagen se subió correctamente a Google Drive.")
                # Eliminar la imagen del repositorio local
                os.remove(file_path)
                print(f"Archivo local {file_path} eliminado.")
            else:
                resp.message("Hubo un error al subir la imagen a Google Drive.")
        else:
            resp.message("Hubo un error al descargar la imagen.")
    else:
        resp.message("No se recibió ninguna imagen.")
        
    return str(resp)

def generate_unique_filename():
    unique_name = str(uuid.uuid4()) + ".jpeg"
    return unique_name

def download_media(media_url, file_path):
    try:
        headers = {"Accept": "image/*"}  # Indicamos que aceptamos cualquier tipo de imagen
        response = requests.get(media_url, auth=(account_sid, auth_token), headers=headers)
        print(f"Request URL: {response.url}")
        print(f"Response Status Code: {response.status_code}")
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                f.write(response.content)
            print(f"Imagen descargada con éxito: {file_path}")
            return True
        else:
            print(f"Error al descargar la imagen: {response.status_code}, URL: {media_url}")
            return False
    except Exception as e:
        print(f"Error al descargar la imagen: {e}")
        return False

def process_and_upload_image(file_path):
    try:
        with open(file_path, 'rb') as f:
            if not f.read(10):
                raise ValueError("El archivo descargado está vacío o no es válido")
        
        with Image.open(file_path) as img:
            if img.format != 'JPEG':
                img = img.convert('RGB')
            img.save(file_path, 'JPEG')
        
        with Image.open(file_path) as img:
            if img.format != 'JPEG':
                raise ValueError("El archivo no se guardó como JPEG correctamente")
        
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