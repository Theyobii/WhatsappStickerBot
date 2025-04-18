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
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')  # Nuevo: ID de número de WhatsApp
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
                message = change['value']['messages'][0]
                sender = message['from']

                if 'image' in message:
                    headers = {
                        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                        "Content-Type": "application/json"
                    }
                    
                    # Descargar imagen
                    image_id = message['image']['id']
                    image_url = f"https://graph.facebook.com/v18.0/{image_id}"
                    response = requests.get(image_url, headers=headers)
                    image_data = requests.get(response.json()['url'], headers=headers).content
                    
                    # Convertir y subir sticker
                    sticker_data = convert_to_sticker(image_data)
                    upload_url = "https://graph.facebook.com/v18.0/media"
                    files = {
                        "file": ("sticker.png", sticker_data, "image/png"),
                        "messaging_product": (None, "whatsapp")
                    }
                    upload_response = requests.post(upload_url, headers=headers, files=files)
                    media_id = upload_response.json()['id']
                    
                    # Enviar sticker
                    send_url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
                    payload = {
                        "messaging_product": "whatsapp",
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