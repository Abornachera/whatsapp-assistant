import os
import json
import requests
import google.generativeai as genai
from flask import Flask, request

app = Flask(__name__)

# --- Credenciales (sin cambios) ---
ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- ¡NUEVO! Lista de números de teléfono autorizados ---
# Añade aquí los números que tendrán permiso para usar el bot.
# IMPORTANTE: Deben ser strings y empezar con el código de país (ej: 57 para Colombia).
AUTHORIZED_NUMBERS = {'573028432451'} # Usamos un set para una búsqueda más eficiente

# --- Configuración de Gemini (sin cambios) ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Gemini configurado correctamente.")
except Exception as e:
    print(f"Error al configurar Gemini: {e}")
    model = None

def get_gemini_response(prompt):
    # ... (sin cambios)
    if not model:
        return "Error: El modelo de IA no está configurado correctamente."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error al generar contenido con Gemini: {e}")
        return "Lo siento, no pude procesar tu solicitud en este momento."

def send_whatsapp_message(to, text):
    # ... (sin cambios)
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
        # ... (sin cambios)
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

                    # --- ¡NUEVO! Lógica de verificación de Whitelist ---
                    if sender_phone in AUTHORIZED_NUMBERS:
                        # Si el número está autorizado, procesa con Gemini
                        print(f"Número autorizado ({sender_phone}) - Mensaje: '{message_text}'")
                        reply_text = get_gemini_response(message_text)
                        print(f"Respuesta de Gemini: '{reply_text}'")
                        send_whatsapp_message(sender_phone, reply_text)
                    else:
                        # Si el número NO está autorizado, envía un mensaje genérico
                        print(f"Número NO AUTORIZADO ({sender_phone}) intentó acceder.")
                        rejection_message = "Hola. He cambiado de número, por favor contáctame a mi nuevo WhatsApp: https://wa.me/573028432451 Gracias."
                        send_whatsapp_message(sender_phone, rejection_message)

        except Exception as e:
            print(f"Ocurrió un error al procesar el mensaje: {e}")
        
        return 'OK', 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)