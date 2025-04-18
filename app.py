from flask import Flask, request, jsonify
import requests
from PIL import Image
import io
import os
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

# Configuración
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')  
MAX_STICKER_SIZE = 512

def smart_crop_to_square(img):
    """Recorta imagen a cuadrado manteniendo el área relevante"""
    width, height = img.size
    if width == height:
        return img
    new_size = min(width, height)
    left = (width - new_size) / 2
    top = (height - new_size) / 2
    right = (width + new_size) / 2
    bottom = (height + new_size) / 2
    return img.crop((left, top, right, bottom))

def convert_to_sticker(image_data):
    """Convierte imagen a sticker optimizado"""
    img = Image.open(io.BytesIO(image_data))
    img = smart_crop_to_square(img)
    if max(img.size) > MAX_STICKER_SIZE:
        img.thumbnail((MAX_STICKER_SIZE, MAX_STICKER_SIZE))
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Token inválido", 403

    data = request.get_json()
    if not data or 'object' not in data or data['object'] != 'whatsapp_business_account':
        return jsonify({"status": "error", "message": "Estructura inválida"}), 400

    try:
        for entry in data['entry']:
            for change in entry['changes']:
                if 'messages' not in change['value']:
                    continue  # Ignora eventos sin mensajes
                
                message = change['value']['messages'][0]
                sender = message['from']

                if 'image' in message:
                    headers = {
                        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                        "Content-Type": "application/json"
                    }
                    
                    # 1. Obtener metadatos de la imagen
                    image_id = message['image']['id']
                    image_url = f"https://graph.facebook.com/v18.0/{image_id}"
                    response = requests.get(image_url, headers=headers)
                    response.raise_for_status()  # Lanza error si HTTP != 200
                    image_json = response.json()

                    if 'url' not in image_json:
                        error_msg = f"API no devolvió URL. Respuesta: {image_json}"
                        print(error_msg)
                        return jsonify({"status": "error", "message": error_msg}), 500

                    # 2. Descargar imagen
                    download_response = requests.get(image_json['url'], headers=headers)
                    download_response.raise_for_status()
                    image_data = download_response.content
                    
                    # 3. Convertir a sticker
                    sticker_data = convert_to_sticker(image_data)
                    
                    # 4. Subir sticker a WhatsApp
                    upload_url = "https://graph.facebook.com/v18.0/media"
                    files = {
                        "file": ("sticker.png", sticker_data, "image/png"),
                        "messaging_product": (None, "whatsapp"),
                        "type": (None, "image/png")
                    }
                    upload_response = requests.post(upload_url, headers=headers, files=files)
                    upload_response.raise_for_status()
                    media_id = upload_response.json()['id']
                    
                    # 5. Enviar sticker al usuario
                    send_url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
                    payload = {
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": sender,
                        "type": "sticker",
                        "sticker": {"id": media_id}
                    }
                    send_response = requests.post(send_url, headers=headers, json=payload)
                    send_response.raise_for_status()

    except requests.exceptions.RequestException as e:
        print(f"Error en la solicitud HTTP: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        print(f"Error inesperado: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)