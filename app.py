import os
import json
import requests
import google.generativeai as genai
from flask import Flask, request
import urllib.parse
import dateparser
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy import create_engine, Column, String, Text, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import datetime

app = Flask(__name__)

ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

AUTHORIZED_NUMBERS = {'573028432451'}

Base = declarative_base()

class ConversationHistory(Base):
    __tablename__ = 'conversation_history'
    id = Column(String, primary_key=True, default=lambda: os.urandom(16).hex())
    sender_phone = Column(String, nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Gemini configurado correctamente.")
except Exception as e:
    print(f"Error al configurar Gemini: {e}")
    model = None

jobstores = {
    'default': SQLAlchemyJobStore(url=DATABASE_URL)
}
scheduler = BackgroundScheduler(jobstores=jobstores)
scheduler.start()
print("Scheduler iniciado y conectado a la base de datos externa.")

def get_conversation_history(sender_phone, limit=10):
    session = Session()
    try:
        history_records = session.query(ConversationHistory).filter_by(sender_phone=sender_phone).order_by(ConversationHistory.timestamp.desc()).limit(limit).all()
        return [{"role": record.role, "parts": [record.content]} for record in reversed(history_records)]
    finally:
        session.close()

def add_to_history(sender_phone, user_message, model_message):
    session = Session()
    try:
        session.add(ConversationHistory(sender_phone=sender_phone, role='user', content=user_message))
        session.add(ConversationHistory(sender_phone=sender_phone, role='model', content=model_message))
        session.commit()
    except SQLAlchemyError as e:
        print(f"Error al guardar en la base de datos: {e}")
        session.rollback()
    finally:
        session.close()

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

def get_gemini_response_with_history(prompt, history):
    if not model: return "Error: El modelo de IA no está configurado."
    try:
        chat = model.start_chat(history=history)
        response = chat.send_message(prompt)
        return response.text
    except Exception as e:
        print(f"Error al generar contenido con Gemini: {e}")
        return "Lo siento, tuve un problema para procesar tu solicitud con el historial."

def search_youtube(query):
    query_formatted = urllib.parse.quote(query)
    search_url = f"https://www.youtube.com/results?search_query={query_formatted}"
    return f"Aquí tienes los resultados para '{query}':\n{search_url}"

def handle_reminder(message, sender_phone):
    task_and_time_str = message.lower().replace('recuérdame', '').replace('recuerdame', '').strip()
    parsed_date = dateparser.parse(task_and_time_str, settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': 'America/Bogota'})
    
    if not parsed_date:
        return "No pude entender la fecha y hora para el recordatorio."
    
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
                            history = get_conversation_history(sender_phone)
                            reply_text = get_gemini_response_with_history(message_text, history)
                            add_to_history(sender_phone, message_text, reply_text)
                        
                        send_whatsapp_message(sender_phone, reply_text)
                    else:
                        rejection_message = "Hola. He cambiado de número, por favor contáctame a mi nuevo WhatsApp: [Tu Nuevo Número Aquí]"
                        send_whatsapp_message(sender_phone, rejection_message)
        except Exception as e:
            print(f"Ocurrió un error al procesar el mensaje: {e}")
        
        return 'OK', 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)