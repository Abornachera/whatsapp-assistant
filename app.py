import os
import json
import requests
import google.generativeai as genai
from flask import Flask, request
import urllib.parse # <- ¡Nueva librería! La usaremos para formatear la búsqueda

app = Flask(__name__)

# --- Credenciales (sin cambios) ---
ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- Lista de números autorizados (sin cambios) ---
AUTHORIZED_NUMBERS = {'573028432451'} 

# --- Configuración de Gemini (sin cambios) ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Gemini configurado correctamente.")
except Exception as e:
    print(f"Error al configurar Gemini: {e}")
    model = None

# --- Función para obtener la respuesta de Gemini (sin cambios) ---
def get_gemini_response(prompt):
    if not model: return "Error: El modelo de IA no está configurado correctamente."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error al generar contenido con Gemini: {e}")
        return "Lo siento, no pude procesar tu solicitud en este momento."

# --- Función para enviar mensajes de WhatsApp (sin cambios) ---
def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        print("Respuesta de Meta:", response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al enviar mensaje: {e}")
        if e.response is not None: print(f"Detalles del error: {e.response.text}")
        return None

# --- ¡NUEVO! Función específica para buscar en YouTube ---
def search_youtube(query):
    # Formateamos la consulta para que sea segura en una URL
    query_formatted = urllib.parse.quote(query)
    # Creamos un enlace de búsqueda directa de YouTube
    search_url = f"https://www.youtube.com/results?search_query={query_formatted}"
    
    # Devolvemos un texto amigable con el enlace
    return f"Aquí tienes los resultados para '{query}':\n{search_url}"

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
                    
                    if sender_phone in AUTHORIZED_NUMBERS:
                        print(f"Número autorizado ({sender_phone}) - Mensaje: '{message_text}'")
                        
                        # --- ¡NUEVO! Lógica para decidir qué hacer con el mensaje ---
                        # Convertimos el mensaje a minúsculas para facilitar la detección de comandos
                        message_lower = message_text.lower()
                        
                        if message_lower.startswith('youtube') or message_lower.startswith('busca en youtube'):
                            # Es una petición de YouTube
                            # Extraemos el término de búsqueda quitando el comando
                            search_query = message_text.lower().replace('busca en youtube', '').replace('youtube', '').strip()
                            reply_text = search_youtube(search_query)
                        
                        else:
                            # Si no es un comando, es una petición para Gemini
                            reply_text = get_gemini_response(message_text)

                        print(f"Enviando respuesta a {sender_phone}...")
                        send_whatsapp_message(sender_phone, reply_text)
                    else:
                        # ... (sin cambios)
                        print(f"Número NO AUTORIZADO ({sender_phone}) intentó acceder.")
                        rejection_message = "Hola. He cambiado de número, por favor contáctame a mi nuevo WhatsApp: [Tu Nuevo Número Aquí]"
                        send_whatsapp_message(sender_phone, rejection_message)

        except Exception as e:
            print(f"Ocurrió un error al procesar el mensaje: {e}")
        
        return 'OK', 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)