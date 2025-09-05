import os
import json
import requests
import google.generativeai as genai # <- Importamos la librería de Gemini
from flask import Flask, request

app = Flask(__name__)

# --- Leemos nuestras credenciales de forma segura ---
ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') # <- Leemos la nueva API Key

# --- Configuramos el cliente de Gemini ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    print("Gemini configurado correctamente.")
except Exception as e:
    print(f"Error al configurar Gemini: {e}")
    model = None

# --- Nueva función para obtener la respuesta de Gemini ---
def get_gemini_response(prompt):
    if not model:
        return "Error: El modelo de IA no está configurado correctamente."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # Maneja errores específicos de la API si es necesario
        print(f"Error al generar contenido con Gemini: {e}")
        return "Lo siento, no pude procesar tu solicitud en este momento."

# --- La función para enviar mensajes de WhatsApp (sin cambios) ---
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
        response.raise_for_status()
        print("Respuesta de Meta:", response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al enviar mensaje: {e}")
        if e.response is not None:
            print(f"Detalles del error: {e.response.text}")
        return None

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Verificación del webhook (sin cambios)
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        else:
            return 'Verification token mismatch', 403

    if request.method == 'POST':
        data = request.get_json()
        print("Datos recibidos:", json.dumps(data, indent=2))

        try:
            if (data.get('entry') and
                data['entry'][0].get('changes') and
                data['entry'][0]['changes'][0].get('value') and
                data['entry'][0]['changes'][0]['value'].get('messages')):
                
                message_data = data['entry'][0]['changes'][0]['value']['messages'][0]
                
                if message_data.get('type') == 'text':
                    sender_phone = message_data['from']
                    message_text = message_data['text']['body']

                    print(f"Mensaje de {sender_phone}: '{message_text}'")

                    # --- ¡AQUÍ ESTÁ LA MAGIA! ---
                    # En lugar del "eco", llamamos a la función de Gemini
                    reply_text = get_gemini_response(message_text)
                    
                    print(f"Respuesta de Gemini: '{reply_text}'")
                    print(f"Enviando respuesta a {sender_phone}...")
                    send_whatsapp_message(sender_phone, reply_text)

        except Exception as e:
            print(f"Ocurrió un error al procesar el mensaje: {e}")
        
        return 'OK', 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)