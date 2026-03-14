#!/usr/bin/env python3
"""
Servidor webhook para el chatbot "Restaurante Sin Apetito"
Recibe datos del chatbot Pickaxe y los guarda en Google Sheets.

Lógica:
- Si el teléfono ya existe en col A: suma 2 puntos en col D, actualiza fecha en col E, actualiza email en col C si lo dio
- Si no existe: nueva fila con teléfono(A), nombre(B), email(C), 2 puntos(D), fecha(E), menú(F)
"""

from flask import Flask, request, jsonify
import json
import os
import base64
import tempfile
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Configuración desde variables de entorno
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1TuYqXbdT2fJ3sARA_0kuY8E3ZfPpsSRj3K8UEA_ToAw")
SHEET_NAME = os.environ.get("SHEET_NAME", "Clientes")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_sheets_service():
    """Obtener el servicio de Google Sheets autenticado."""
    # Las credenciales se cargan desde variable de entorno (JSON en Base64 o JSON directo)
    credentials_env = os.environ.get("GOOGLE_CREDENTIALS", "")
    
    if not credentials_env:
        raise ValueError("Variable de entorno GOOGLE_CREDENTIALS no configurada")
    
    # Intentar decodificar como Base64 primero
    try:
        credentials_json = base64.b64decode(credentials_env).decode("utf-8")
    except Exception:
        # Si falla, asumir que ya es JSON directo
        credentials_json = credentials_env
    
    credentials_info = json.loads(credentials_json)
    
    creds = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    return service.spreadsheets()

def get_all_data(sheets):
    """Obtener todos los datos del sheet."""
    result = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:F"
    ).execute()
    return result.get("values", [])

def find_phone_row(data, phone):
    """Buscar si el teléfono ya existe. Retorna el índice de fila (0-based) o -1."""
    phone_clean = str(phone).strip().replace(" ", "").replace("-", "")
    for i, row in enumerate(data):
        if row and len(row) > 0:
            existing_phone = str(row[0]).strip().replace(" ", "").replace("-", "")
            if existing_phone == phone_clean:
                return i
    return -1

def update_existing_client(sheets, row_index, email, menu):
    """Actualizar cliente existente: sumar 2 puntos, actualizar fecha y email si se proporcionó."""
    sheet_row = row_index + 2  # +1 por 1-indexed, +1 por encabezado
    
    result = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A{sheet_row}:F{sheet_row}"
    ).execute()
    
    current_row = result.get("values", [[]])[0] if result.get("values") else []
    
    current_points = 0
    if len(current_row) > 3 and current_row[3]:
        try:
            current_points = int(current_row[3])
        except (ValueError, TypeError):
            current_points = 0
    
    new_points = current_points + 2
    today = datetime.now().strftime("%Y-%m-%d")
    
    updates = []
    
    updates.append({
        "range": f"{SHEET_NAME}!D{sheet_row}",
        "values": [[new_points]]
    })
    
    updates.append({
        "range": f"{SHEET_NAME}!E{sheet_row}",
        "values": [[today]]
    })
    
    if email and email.strip() and email.strip() != "no proporcionado" and "@" in email:
        updates.append({
            "range": f"{SHEET_NAME}!C{sheet_row}",
            "values": [[email.strip()]]
        })
    
    if menu and menu.strip():
        updates.append({
            "range": f"{SHEET_NAME}!F{sheet_row}",
            "values": [[menu.strip()]]
        })
    
    body = {
        "valueInputOption": "USER_ENTERED",
        "data": updates
    }
    sheets.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body=body
    ).execute()
    
    return new_points

def add_new_client(sheets, phone, name, email, menu):
    """Agregar un nuevo cliente al sheet."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    new_row = [
        str(phone).strip(),
        str(name).strip() if name else "",
        str(email).strip() if email and "@" in str(email) else "",
        2,
        today,
        str(menu).strip() if menu else ""
    ]
    
    body = {"values": [new_row]}
    
    sheets.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:F",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

def parse_pickaxe_data(raw_data_field, data):
    """Parsear el campo 'data' que envía Pickaxe en varios formatos posibles."""
    import re
    
    if not raw_data_field:
        return data
    
    # Intentar parsear como JSON primero
    try:
        if isinstance(raw_data_field, str):
            parsed_data = json.loads(raw_data_field)
            if isinstance(parsed_data, dict):
                data.update(parsed_data)
                return data
    except (json.JSONDecodeError, TypeError):
        pass
    
    raw_str = str(raw_data_field).strip()
    KNOWN_KEYS = r'(?:nombre|name|telefono|phone|tel|email|correo|mail|menu|platos|pedido|order)'
    
    # Detectar si el string contiene claves conocidas con formato clave: valor
    has_named_keys = bool(re.search(KNOWN_KEYS + r'\s*:', raw_str, re.IGNORECASE))
    
    if has_named_keys:
        # Extraer cada campo usando regex que busca la clave seguida de su valor
        # hasta la siguiente clave conocida o el final del string
        # Esto funciona independientemente del separador (| o ,)
        pattern = re.compile(
            r'(' + KNOWN_KEYS + r')\s*:\s*(.+?)'
            r'(?=\s*[|,]\s*' + KNOWN_KEYS + r'\s*:|$)',
            re.IGNORECASE | re.DOTALL
        )
        matches = pattern.findall(raw_str)
        menu_parts = []
        
        for key, value in matches:
            key = key.lower().strip()
            value = value.strip().strip(',').strip('|').strip()
            if key in ['nombre', 'name']:
                data['nombre'] = value
            elif key in ['telefono', 'phone', 'tel', 'telephone']:
                data['telefono'] = value
            elif key in ['email', 'correo', 'mail']:
                data['email'] = value
            elif key in ['menu', 'platos', 'pedido', 'order']:
                # El menú puede contener pipes como separadores de platos
                data['menu'] = value
        
        # Si hay teléfono al inicio antes de las claves (formato: "655999888, nombre: X")
        if not data.get('telefono'):
            first_token_match = re.match(r'^([+\d\s\-]{7,15})\s*[,|]', raw_str)
            if first_token_match:
                data['telefono'] = first_token_match.group(1).replace(' ', '').replace('-', '')
        
        return data
    
    # Sin claves nombradas: intentar formato posicional con pipes
    pipe_parts = [p.strip() for p in raw_str.split('|')]
    if len(pipe_parts) >= 2:
        data['telefono'] = pipe_parts[0].strip()
        data['nombre'] = pipe_parts[1].strip() if len(pipe_parts) > 1 else ''
        data['email'] = pipe_parts[2].strip() if len(pipe_parts) > 2 else ''
        data['menu'] = ' | '.join(pipe_parts[3:]).strip() if len(pipe_parts) > 3 else ''
        return data
    
    # Formato posicional con comas
    comma_parts = [p.strip() for p in raw_str.split(',')]
    if len(comma_parts) >= 2:
        data['telefono'] = comma_parts[0].strip()
        data['nombre'] = comma_parts[1].strip() if len(comma_parts) > 1 else ''
        data['email'] = comma_parts[2].strip() if len(comma_parts) > 2 else ''
        data['menu'] = ', '.join(comma_parts[3:]).strip() if len(comma_parts) > 3 else ''
        return data
    
    # Fallback: asumir que todo es el teléfono
    data['telefono'] = raw_str
    return data

@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "Restaurante Sin Apetito - Google Sheets Webhook",
        "version": "1.0.0"
    })

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    """
    Endpoint principal del webhook.
    Acepta datos del chatbot y los guarda en Google Sheets.
    """
    data = {}
    
    if request.method == "POST":
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
    else:
        data = request.args.to_dict()
    
    # Parsear el campo 'data' de Pickaxe si existe
    raw_data_field = data.get("data", "")
    if raw_data_field:
        data = parse_pickaxe_data(raw_data_field, data)
    
    # Extraer campos con múltiples nombres posibles
    telefono = (data.get("telefono") or data.get("phone") or data.get("tel") or
                data.get("telephone") or "").strip()
    nombre = (data.get("nombre") or data.get("name") or data.get("cliente") or "").strip()
    email = (data.get("email") or data.get("correo") or data.get("mail") or "").strip()
    menu = (data.get("menu") or data.get("platos") or data.get("pedido") or
            data.get("order") or data.get("dishes") or "").strip()
    
    # Si no hay teléfono, buscar en cualquier campo numérico
    if not telefono:
        for key, value in data.items():
            if value and len(str(value)) >= 9 and str(value).replace('+', '').replace(' ', '').replace('-', '').isdigit():
                telefono = str(value).strip()
                break
    
    if not telefono:
        return jsonify({
            "success": False,
            "error": "Campo 'telefono' requerido",
            "received_fields": list(data.keys())
        }), 400
    
    try:
        sheets = get_sheets_service()
        all_data = get_all_data(sheets)
        
        data_rows = all_data
        if all_data and len(all_data) > 0:
            first_row = all_data[0]
            if first_row and len(first_row) > 0:
                first_cell = str(first_row[0]).lower()
                if any(word in first_cell for word in ["teléfono", "telefono", "phone", "tel", "nombre", "name"]):
                    data_rows = all_data[1:]
        
        row_index = find_phone_row(data_rows, telefono)
        
        if row_index >= 0:
            new_points = update_existing_client(sheets, row_index, email, menu)
            action = "updated"
            message = f"Cliente actualizado. Nuevos puntos: {new_points}"
        else:
            add_new_client(sheets, telefono, nombre, email, menu)
            action = "created"
            message = "Nuevo cliente registrado con 2 puntos"
        
        return jsonify({
            "success": True,
            "action": action,
            "message": message,
            "data": {
                "telefono": telefono,
                "nombre": nombre,
                "email": email
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
