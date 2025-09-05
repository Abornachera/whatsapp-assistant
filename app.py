import os
import requests
import uuid
from flask import Flask, request
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import google.generativeai as genai

app = Flask(__name__)

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
Base = declarative_base()

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    message = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

def get_history(user_id):
    session = Session()
    messages = session.query(Conversation).filter_by(user_id=user_id).order_by(Conversation.timestamp.asc()).all()
    session.close()
    history = []
    for m in messages:
        history.append({"role": m.role, "parts": [m.message]})
    return history

def save_message(user_id, role, message):
    session = Session()
    msg = Conversation(user_id=user_id, role=role, message=message)
    session.add(msg)
    session.commit()
    session.close()

def get_gemini_response_with_history(prompt, history):
    if not model:
        return "Error: modelo no configurado."
    try:
        messages = history + [{"role": "user", "parts": [prompt]}]
        response = model.generate_content(messages)
        return response.text
    except Exception as e:
        print(f"Error con Gemini: {e}")
        return "Lo siento, ocurrió un problema procesando tu solicitud."

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge
    return "Error de verificación", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for message in messages:
                    if message.get("type") == "text":
                        user_id = message["from"]
                        user_message = message["text"]["body"]

                        save_message(user_id, "user", user_message)
                        history = get_history(user_id)
                        response_text = get_gemini_response_with_history(user_message, history)
                        save_message(user_id, "model", response_text)

                        url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
                        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
                        payload = {
                            "messaging_product": "whatsapp",
                            "to": user_id,
                            "text": {"body": response_text},
                        }
                        requests.post(url, headers=headers, json=payload)
    return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
