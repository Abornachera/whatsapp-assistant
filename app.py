import os
import json
import requests # <- Importamos la nueva librería
from flask import Flask, request

app = Flask(__name__)

# --- Leemos nuestras credenciales desde las variables de entorno de Render ---
ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')

# --- Función para enviar el mensaje de respuesta ---
def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": text}
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status() # Lanza un error si la petición falló
        print("Respuesta de Meta:", response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al enviar mensaje: {e}")
        # Imprime más detalles si la respuesta tiene contenido
        if e.response is not None:
            print(f"Detalles del error: {e.response.text}")
        return None

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        else:
            return 'Verification token mismatch', 403

    if request.method == 'POST':
        data = request.get_json()
        print("Datos recibidos:", json.dumps(data, indent=2))

        # --- Lógica para procesar el mensaje ---
        try:
            # Nos aseguramos de que sea un mensaje de usuario y no una notificación de estado
            if (data.get('entry') and
                data['entry'][0].get('changes') and
                data['entry'][0]['changes'][0].get('value') and
                data['entry'][0]['changes'][0]['value'].get('messages')):
                
                message_data = data['entry'][0]['changes'][0]['value']['messages'][0]
                
                # Verificamos que sea un mensaje de texto
                if message_data.get('type') == 'text':
                    sender_phone = message_data['from']
                    message_text = message_data['text']['body']

                    print(f"Mensaje de {sender_phone}: '{message_text}'")

                    # --- Aquí creamos el "eco" ---
                    reply_text = f"Tú dijiste: {message_text}" # La respuesta del bot
                    
                    print(f"Enviando respuesta a {sender_phone}...")
                    send_whatsapp_message(sender_phone, reply_text)

        except Exception as e:
            print(f"Ocurrió un error al procesar el mensaje: {e}")
        
        return 'OK', 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)