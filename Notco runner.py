import csv
import os
import time
import streamlit as st

# Configuración inicial de la página
st.set_page_config(page_title="Agente NotCo (Nota)", page_icon="🤖")

# Intento de importación del SDK
try:
    from google import genai
    from google.genai import types
except Exception as e:
    st.error(f"Error al importar el SDK de Google GenAI: {e}")
    st.info("Asegúrate de que 'google-genai' esté escrito correctamente en tu archivo requirements.txt")
    st.stop()

# Constantes
DEFAULT_PROMPT_FILE = "prompt.txt"
DEFAULT_CATALOGO_FILE = "catalogo_notco.csv"
CATALOGO_PLACEHOLDER = "{CATALOGO_TABLE}"

def format_price(raw):
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

@st.cache_data
def load_system_prompt(prompt_path, catalogo_path):
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    if CATALOGO_PLACEHOLDER in prompt_text:
        table = build_catalog_table(catalogo_path)
        prompt_text = prompt_text.replace(CATALOGO_PLACEHOLDER, table)
    
    return prompt_text

# Interfaz principal de Streamlit
st.title("🤖 Probador del Agente de NotCo (Nota)")

# Obtener API Key
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("Falta configurar la llave GEMINI_API_KEY en los Secrets de Streamlit.")
    st.stop()

if not os.path.exists(DEFAULT_PROMPT_FILE) or not os.path.exists(DEFAULT_CATALOGO_FILE):
    st.error("No se encontraron los archivos prompt.txt o catalogo_notco.csv en el repositorio.")
    st.stop()

# Cargar System Prompt
system_prompt = load_system_prompt(DEFAULT_PROMPT_FILE, DEFAULT_CATALOGO_FILE)

# Inicializar cliente si no existe
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=api_key)

# Modelo principal recomendado para producción
MODEL_NAME = "gemini-3.5-flash-lite"

# Inicializar sesión de chat si no existe
if "chat" not in st.session_state:
    st.session_state.chat = st.session_state.client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar historial de mensajes en pantalla
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Entrada de texto del usuario
if prompt := st.chat_input("Escribe tu consulta a Nota..."):
    # Guardar y mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generar respuesta
    with st.chat_message("assistant"):
        with st.spinner("Nota está respondiendo..."):
            try:
                # Envío directo al chat gestionado por la librería
                response = st.session_state.chat.send_message(prompt)
                
                if response and response.text:
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                else:
                    st.error("La API no devolvió contenido en la respuesta.")
            except Exception as e:
                # Mostramos el error real devuelto por Google para diagnosticar de inmediato
                st.error(f"Detalle del error devuelto por la API: {e}")
