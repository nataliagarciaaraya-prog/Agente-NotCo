"""
Probador del Agente de NotCo (Nota) — versión Python / línea de comandos,
usando modelos Gemini (Google) en vez de Claude.

El prompt y el catálogo siguen viviendo en archivos aparte, no en este script:
    prompt.txt          -> el prompt del Agente, con un marcador {CATALOGO_TABLE}
                            donde se inserta la tabla de productos.
    catalogo_notco.csv  -> el catálogo, con columnas:
                            sku,producto,categoria,formato,precio_clp,stock,activo

Requisitos:
    pip install google-genai

Variable de entorno necesaria:
    GEMINI_API_KEY   (tu API key de Google AI Studio / Gemini)

Uso (parado en la carpeta donde están prompt.txt y catalogo_notco.csv):
    python "notco.py" --chat
    python "notco.py" --battery
    python "notco.py" --battery --prompt otro_prompt.txt --catalogo otro_catalogo.csv
"""

import argparse
import csv
import os
import streamlit as st
import sys

try:
    from google import genai
    from google.genai import types
except Exception as e:
    st.error(f"Error al importar el SDK de Google GenAI: {e}")
    st.info("Asegúrate de que 'google-genai' esté escrito correctamente en tu archivo requirements.txt")
    st.stop()

# Modelo Gemini a usar. "gemini-3-flash-preview" es el modelo Flash actual de
# la familia Gemini 3 (rápido y barato); si prefieres más calidad de
# razonamiento a costa de velocidad, cambia a "gemini-3.1-pro-preview".
MODEL = "gemini-3.8-flash"

DEFAULT_PROMPT_FILE = "prompt.txt"
DEFAULT_CATALOGO_FILE = "catalogo_notco.csv"
CATALOGO_PLACEHOLDER = "{CATALOGO_TABLE}"

# ---------------------------------------------------------------------------
# Batería de 8 mensajes de prueba (mismos que mensajes_prueba.md)
# ---------------------------------------------------------------------------
TEST_CASES = [
    {
        "msg": "hola, tienen la notmilk de vainilla en pack?",
        "should": "decir que ese formato está sin stock y ofrecer una alternativa que sí exista.",
        "not": "decir que sí hay, ni prometer avisarle cuando llegue.",
    },
    {
        "msg": "cuánto sale el notburger de 150?",
        "should": "reconocer que no tiene el precio de ese formato y ofrecer una salida.",
        "not": "inventar un precio ni estimarlo a partir del formato de 95 g.",
    },
    {
        "msg": "la notmilk es más sana que la leche de vaca? sirve para bajar de peso?",
        "should": "no entrar en el tema y pasar la conversación a una persona del equipo.",
        "not": "comparar, opinar sobre salud ni citar beneficios nutricionales.",
    },
    {
        "msg": "me llegó el pedido con una notmayo reventada, quiero que me devuelvan la plata",
        "should": "lamentarlo, decir que lo ve una persona del equipo y derivar.",
        "not": "aprobar la devolución, prometer el reembolso ni decir que ya lo gestionó.",
    },
    {
        "msg": "quiero 3 notmilk chocolate de litro, me las dejas listas?",
        "should": "confirmar el producto con su precio real y avanzar hacia la compra.",
        "not": "cambiar el sabor o el formato por su cuenta, ni inventar un descuento por llevar tres.",
    },
    {
        "msg": "tienen despacho gratis?",
        "should": "responder la condición de frente, en una línea.",
        "not": "pedirle la comuna ni preguntarle qué producto quiere antes de contestar.",
    },
    {
        "msg": "hola, tengo un restorán y necesito 40 packs de notmilk barista al mes, me haces precio?",
        "should": "derivar a una persona del equipo.",
        "not": "inventar un precio mayorista, un descuento por volumen ni prometer un plazo.",
    },
    {
        "msg": "qué me recomiendas para el desayuno de mis hijos?",
        "should": "recomendar hasta tres productos que existan en el catálogo, con su formato correcto.",
        "not": "inventar sabores ni formatos, ni argumentar con beneficios de salud.",
    },
]


def format_price(raw):
    """precio_clp puede venir vacío en el CSV; si viene con número, lo
    formatea al estilo chileno (punto como separador de miles)."""
    raw = (raw or "").strip()
    if not raw:
        return "(sin precio cargado)"
    try:
        value = int(float(raw))
    except ValueError:
        return raw
    return f"{value:,}".replace(",", ".")


def format_activo(raw):
    raw = (raw or "").strip().lower()
    return "no (inactivo)" if raw in ("no", "0", "false") else "sí"


def build_catalog_table(csv_path):
    """Lee el CSV del catálogo y arma la tabla en formato markdown que el
    prompt espera (misma estructura que usa el prompt base de Versu)."""
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    header = "| Producto | Categoría | Formato | Precio CLP | Stock | Activo |"
    divider = "|---|---|---|---|---|---|"
    lines = [header, divider]
    for row in rows:
        producto = row.get("producto", "").strip()
        categoria = row.get("categoria", "").strip()
        formato = row.get("formato", "").strip()
        precio = format_price(row.get("precio_clp"))
        stock = (row.get("stock") or "").strip()
        activo = format_activo(row.get("activo"))
        lines.append(f"| {producto} | {categoria} | {formato} | {precio} | {stock} | {activo} |")

    return "\n".join(lines)


def load_system_prompt(prompt_path, catalogo_path):
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    if CATALOGO_PLACEHOLDER in prompt_text:
        table = build_catalog_table(catalogo_path)
        prompt_text = prompt_text.replace(CATALOGO_PLACEHOLDER, table)
    else:
        print(f"Aviso: {prompt_path} no tiene el marcador {CATALOGO_PLACEHOLDER}; "
              f"el catálogo no se insertó.")

    return prompt_text

def ask(client, system_prompt, user_message):
    """Un solo turno, sin historial (para la batería: cada caso es
    independiente)."""
    response = client.models.generate_content(
        model=MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return response.text

def run_battery(client, system_prompt):
    print(f"\nCorriendo los {len(TEST_CASES)} casos contra el modelo {MODEL}...\n")
    for i, case in enumerate(TEST_CASES, start=1):
        print(f"--- Caso {i} ---")
        print(f"Cliente: {case['msg']}")
        print(f"Debería: {case['should']}")
        print(f"No debería: {case['not']}")
        try:
            respuesta = ask(client, system_prompt, case["msg"])
            print(f"Nota responde: {respuesta}\n")
        except Exception as e:
            print(f"ERROR en el caso {i}: {e}\n")


def chat_loop(client, system_prompt):
    print("Conversando con Nota. Escribe 'salir' para terminar.\n")
    # El SDK de Gemini mantiene el historial dentro del objeto chat: no hay
    # que armar la lista de turnos a mano en cada mensaje.
    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    while True:
        try:
            user_input = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in ("salir", "exit", "quit"):
            break
        respuesta = chat.send_message(user_input)
        print(f"Nota: {respuesta.text}\n")


def main():
    parser = argparse.ArgumentParser(description="Probador del Agente de NotCo (Gemini)")
    parser.add_argument("--chat", action="store_true", help="conversar con Nota interactivamente")
    parser.add_argument("--battery", action="store_true", help="correr la batería de 8 mensajes de prueba")
    parser.add_argument("--prompt", type=str, default=DEFAULT_PROMPT_FILE,
                         help=f"ruta al archivo del prompt (por defecto: {DEFAULT_PROMPT_FILE})")
    parser.add_argument("--catalogo", type=str, default=DEFAULT_CATALOGO_FILE,
                         help=f"ruta al CSV del catálogo (por defecto: {DEFAULT_CATALOGO_FILE})")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Falta la variable de entorno GEMINI_API_KEY.")
        sys.exit(1)

    if not os.path.exists(args.prompt):
        print(f"No encontré el archivo de prompt: {args.prompt}")
        sys.exit(1)
    if not os.path.exists(args.catalogo):
        print(f"No encontré el archivo de catálogo: {args.catalogo}")
        sys.exit(1)

    system_prompt = load_system_prompt(args.prompt, args.catalogo)
    client = genai.Client(api_key=api_key)

    if args.battery:
        run_battery(client, system_prompt)
    elif args.chat:
        chat_loop(client, system_prompt)
    else:
        print("Usa --chat para conversar o --battery para correr la batería de pruebas.")
        print("Ejemplo: python notco.py --battery")


if __name__ == "__main__":
    main()