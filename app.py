from flask import Flask, request, jsonify
import requests
from PIL import Image
import io
import os
from datetime import datetime
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()       

# Configuración
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
STICKER_COMMAND = "/sticker"
MAX_STICKER_SIZE = 512  # Tamaño máximo recomendado para stickers en WhatsApp

def smart_crop_to_square(img):
    """Recorta la imagen a cuadrado manteniendo el área relevante"""
    width, height = img.size
    
    # Si ya es cuadrada, retornar original
    if width == height:
        return img
    
    # Determinar el tamaño del cuadrado (usar el lado más corto)
    new_size = min(width, height)
    
    # Calcular coordenadas para recorte centrado
    left = (width - new_size) / 2
    top = (height - new_size) / 2
    right = (width + new_size) / 2
    bottom = (height + new_size) / 2
    
    return img.crop((left, top, right, bottom))

def convert_to_sticker(image_data):
    """Convierte imagen a sticker con recorte inteligente"""
    img = Image.open(io.BytesIO(image_data))
    
    # 1. Recortar a cuadrado manteniendo el área importante
    img = smart_crop_to_square(img)
    
    # 2. Redimensionar si es muy grande (sin superar el límite de WhatsApp)
    if max(img.size) > MAX_STICKER_SIZE:
        img.thumbnail((MAX_STICKER_SIZE, MAX_STICKER_SIZE))
    
    # Guardar como PNG (mantiene transparencia si existe)
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    return output.getvalue()

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Token inválido", 403
    
    data = request.get_json()
    
    try:
        if data['object'] == 'whatsapp_business_account':
            for entry in data['entry']:
                for change in entry['changes']:
                    message = change['value']['messages'][0]
                    sender = message['from']
                    
                    if 'text' in message and message['text']['body'].lower() == STICKER_COMMAND:
                        if 'image' in message:
                            # Descargar imagen
                            headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
                            image_id = message['image']['id']
                            image_url = f"https://graph.facebook.com/v13.0/{image_id}"
                            response = requests.get(image_url, headers=headers)
                            image_data = requests.get(response.json()['url'], headers=headers).content
                            
                            # Convertir a sticker
                            sticker_data = convert_to_sticker(image_data)
                            
                            # Subir a WhatsApp
                            upload_url = "https://graph.facebook.com/v13.0/media"
                            files = {
                                "file": ("sticker.png", sticker_data, "image/png"),
                                "messaging_product": (None, "whatsapp"),
                                "type": (None, "image/png")
                            }
                            upload_response = requests.post(upload_url, headers=headers, files=files)
                            media_id = upload_response.json()['id']
                            
                            # Enviar sticker
                            send_url = f"https://graph.facebook.com/v13.0/{entry['id']}/messages"
                            payload = {
                                "messaging_product": "whatsapp",
                                "recipient_type": "individual",
                                "to": sender,
                                "type": "sticker",
                                "sticker": {"id": media_id}
                            }
                            requests.post(send_url, headers=headers, json=payload)
                            
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)