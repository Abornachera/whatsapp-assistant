import os
import json
import requests
import google.generativeai as genai
from flask import Flask, request
import urllib.parse
import dateparser
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

app = Flask(__name__)

ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

AUTHORIZED_NUMBERS = {'573028432451'}

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Gemini configurado correctamente.")
except Exception as e:
    print(f"Error al configurar Gemini: {e}")
    model = None

persistent_data_dir = '/var/data'
os.makedirs(persistent_data_dir, exist_ok=True)
persistent_db_path = os.path.join(persistent_data_dir, 'scheduler.db')

jobstores = {
    'default': SQLAlchemyJobStore(url=f'sqlite:///{persistent_db_path}')
}
scheduler = BackgroundScheduler(jobstores=jobstores)
scheduler.start()
print(f"Scheduler iniciado. Tareas guardadas en: {persistent_db_path}")

def send_whatsapp_message(to, text):
    print(f"Intentando enviar mensaje a {to}: '{text}'")
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

def get_gemini_response(prompt):
    if not model: return "Error: El modelo de IA no está configurado."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error al generar contenido con Gemini: {e}")
        return "Lo siento, no pude procesar tu solicitud."

def search_youtube(query):
    query_formatted = urllib.parse.quote(query)
    search_url = f"https://www.youtube.com/results?search_query={query_formatted}"
    return f"Aquí tienes los resultados para '{query}':\n{search_url}"

def handle_reminder(message, sender_phone):
    task_and_time_str = message.lower().replace('recuérdame', '').replace('recuerdame', '').strip()
    parsed_date = dateparser.parse(task_and_time_str, settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': 'America/Bogota'})
    
    if not parsed_date:
        return "No pude entender la fecha y hora para el recordatorio. Intenta ser más específico, por ejemplo: 'recuérdame comprar pan mañana a las 5 pm'."

    task = task_and_time_str.replace(parsed_date.strftime('%H:%M'), '').replace(parsed_date.strftime('%I:%M %p'), '').strip()

    scheduler.add_job(send_whatsapp_message, 'date', run_date=parsed_date, args=[sender_phone, f"¡RECORDATORIO! ✨\n\n{task}"])
    
    print(f"Recordatorio programado para {sender_phone} en la fecha {parsed_date}: {task}")
    
    return f"¡Entendido! Te recordaré '{task}' el {parsed_date.strftime('%d de %B a las %I:%M %p')}."

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
                        message_lower = message_text.lower()
                        reply_text = ""
                        
                        if message_lower.startswith('recuérdame') or message_lower.startswith('recuerdame'):
                            reply_text = handle_reminder(message_text, sender_phone)
                        elif message_lower.startswith('youtube') or message_lower.startswith('busca en youtube'):
                            search_query = message_text.lower().replace('busca en youtube', '').replace('youtube', '').strip()
                            reply_text = search_youtube(search_query)
                        else:
                            reply_text = get_gemini_response(message_text)

                        send_whatsapp_message(sender_phone, reply_text)
                    else:
                        print(f"Número NO AUTORIZADO ({sender_phone}) intentó acceder.")
                        rejection_message = "Hola. He cambiado de número, por favor contáctame a mi nuevo WhatsApp: [Tu Nuevo Número Aquí]"
                        send_whatsapp_message(sender_phone, rejection_message)

        except Exception as e:
            print(f"Ocurrió un error al procesar el mensaje: {e}")
        
        return 'OK', 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)