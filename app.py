import os
import uuid
import requests
from flask import Flask, request
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import google.generativeai as genai
import pytz

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
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

WHITELIST = {num.strip() for num in os.getenv("WHITELIST", "").split(",") if num.strip()}

FALLBACK_MESSAGE = "Lo siento, cambié de número, escríbeme al wa.me/573028432451 Gracias."

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"Error enviando WhatsApp: {e}")

def get_history(user_id, limit=20):
    with Session() as session:
        rows = (
            session.query(Conversation)
            .filter_by(user_id=user_id)
            .order_by(Conversation.timestamp.asc())
            .limit(limit)
            .all()
        )
        return [{"role": row.role, "parts": [row.message]} for row in rows]

def save_message(user_id, role, message):
    with Session() as session:
        session.add(Conversation(user_id=user_id, role=role, message=message))
        session.commit()

def gemini_reply(user_message, user_id):
    history = get_history(user_id)
    messages = history + [{"role": "user", "parts": [user_message]}]
    try:
        resp = model.generate_content(messages)
        return resp.text
    except Exception as e:
        print(f"Error Gemini: {e}")
        return "Ocurrió un problema generando la respuesta."

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
                for message in value.get("messages", []):
                    if message.get("type") == "text":
                        user_id = message["from"]
                        body = message["text"]["body"]

                        if user_id not in WHITELIST:
                            send_whatsapp_message(user_id, FALLBACK_MESSAGE)
                            continue

                        reply = gemini_reply(body, user_id)

                        save_message(user_id, "user", body)
                        save_message(user_id, "model", reply)
                        send_whatsapp_message(user_id, reply)
    return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
