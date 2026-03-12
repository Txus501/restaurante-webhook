# Restaurante Sin Apetito — Webhook Google Sheets

Servidor webhook que recibe datos del chatbot Pickaxe y los guarda en Google Sheets.

## Variables de entorno requeridas

| Variable | Descripción |
|---|---|
| `GOOGLE_CREDENTIALS` | JSON de la cuenta de servicio codificado en Base64 |
| `SPREADSHEET_ID` | ID del Google Sheet (opcional, ya configurado por defecto) |
| `SHEET_NAME` | Nombre de la pestaña (opcional, por defecto "Clientes") |

## Endpoint

- `GET /` — Health check
- `POST /webhook` — Recibe datos del chatbot y los guarda en Sheets

## Lógica de negocio

- Si el teléfono **ya existe**: suma 2 puntos, actualiza fecha y email si se proporcionó
- Si el teléfono **no existe**: crea nueva fila con todos los datos y 2 puntos iniciales
