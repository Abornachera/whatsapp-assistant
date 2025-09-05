import os
import json
from flask import Flask, request

# Inicializamos Flask
app = Flask(__name__)

# Token de verificación (tú inventas esta cadena de texto)
VERIFY_TOKEN ='KJKLopiperikkc54345642'

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # --- Verificación del Webhook (se usa solo una vez) ---
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        else:
            return 'Verification token mismatch', 403

    # --- Recepción de mensajes de WhatsApp ---
    if request.method == 'POST':
        data = request.get_json()
        print("Datos recibidos:", json.dumps(data, indent=2)) # Imprimimos los datos en la terminal

        # Aquí irá toda la lógica para procesar el mensaje
        # (Fases futuras del proyecto)

        return 'OK', 200

if __name__ == "__main__":
    # El puerto 10000 es el que Render.com usa por defecto
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)