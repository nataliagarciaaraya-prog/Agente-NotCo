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

# Inicializar Cliente de Gemini
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=api_key)

# Inicializar Historial
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar historial de mensajes en pantalla
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# UN SOLO chat_input en todo el script
if prompt := st.chat_input("Escribe tu consulta a Nota..."):
    # Guardar y mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generar respuesta
    with st.chat_message("assistant"):
        with st.spinner("Nota está respondiendo..."):
            response_text = None
            
            # Intentar generar contenido directamente con el cliente
            # (evita acumular estados de chat desactualizados)
            models_to_try = ["gemini-1.5-flash", "gemini-2.0-flash"]
            
            # Construir historial para la llamada
            contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in st.session_state.messages]
            
            for model_name in models_to_try:
                try:
                    for attempt in range(2):
                        try:
                            res = st.session_state.client.models.generate_content(
                                model=model_name,
                                contents=contents,
                                config=types.GenerateContentConfig(system_instruction=system_prompt)
                            )
                            response_text = res.text
                            break
                        except Exception as e:
                            if ("503" in str(e) or "UNAVAILABLE" in str(e)) and attempt == 0:
                                time.sleep(1.5)
                            else:
                                raise e
                    if response_text:
                        break
                except Exception:
                    continue

            if response_text:
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            else:
                st.error("Los servidores de la API están con alta demanda en este momento. Por favor, intenta de nuevo en unos segundos.")