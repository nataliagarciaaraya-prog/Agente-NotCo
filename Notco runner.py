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

# Lista de modelos priorizados (si el primero está saturado, prueba el siguiente)
MODELS_TO_TRY = ["gemini-3.8-flash", "gemini-1.5-flash"]
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

# Obtener API Key de Secrets o Variable de Entorno
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("Falta configurar la llave GEMINI_API_KEY en los Secrets de Streamlit.")
    st.stop()

if not os.path.exists(DEFAULT_PROMPT_FILE) or not os.path.exists(DEFAULT_CATALOGO_FILE):
    st.error("No se encontraron los archivos prompt.txt o catalogo_notco.csv en el repositorio.")
    st.stop()

# Cargar System Prompt
system_prompt = load_system_prompt(DEFAULT_PROMPT_FILE, DEFAULT_CATALOGO_FILE)

import time
from google.genai import errors

# ... (Mantiene tu código de lectura de prompt y catálogo) ...

# 1. Definir lista de modelos de producción estables
# Si uno no responde por sobredemanda, la app prueba con el siguiente automáticamente
AVAILABLE_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash"]

# Inicializar Cliente de Gemini
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=api_key)

# Función para forzar la creación limpia de un Chat
def create_new_chat(model_name):
    st.session_state.current_model = model_name
    st.session_state.chat = st.session_state.client.chats.create(
        model=model_name,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )

# Si no hay chat o el modelo guardado no está en la lista válida, creamos uno nuevo
if "chat" not in st.session_state or "current_model" not in st.session_state:
    create_new_chat(AVAILABLE_MODELS[0])

if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar historial de mensajes
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Entrada de texto del usuario
if prompt := st.chat_input("Escribe tu consulta a Nota..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Respuesta del agente
    with st.chat_message("assistant"):
        with st.spinner("Nota está respondiendo..."):
            response_text = None
            
            # Recorrer modelos si el servidor de uno está ocupado (503)
            for model in AVAILABLE_MODELS:
                try:
                    # Si necesitamos cambiar de modelo en la sesión, re-inicializamos
                    if st.session_state.current_model != model:
                        create_new_chat(model)
                    
                    # Intentar envío con 2 reintentos rápidos por modelo
                    for attempt in range(2):
                        try:
                            res = st.session_state.chat.send_message(prompt)
                            response_text = res.text
                            break
                        except Exception as inner_e:
                            if ("503" in str(inner_e) or "UNAVAILABLE" in str(inner_e)) and attempt == 0:
                                time.sleep(1.5)  # Breve pausa antes de reintentar
                            else:
                                raise inner_e

                    if response_text:
                        break  # Si obtuvimos respuesta exitosa, salimos del bucle principal

                except Exception as model_err:
                    # Si falla este modelo, el bucle intentará automáticamente con el siguiente de la lista
                    continue

            # Mostrar respuesta o error final
            if response_text:
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            else:
                st.error("Los servidores de la API están experimentando alta demanda en este momento. Por favor, intenta tu consulta nuevamente en unos segundos.")


# Mostrar historial de mensajes en pantalla
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Entrada de texto del usuario
if prompt := st.chat_input("Escribe tu consulta a Nota..."):
    # Mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Respuesta del agente con lógica de reintentos y fallback de modelos
    with st.chat_message("assistant"):
        with st.spinner("Nota está respondiendo..."):
            response_text = None
            
            for model in MODELS_TO_TRY:
                if st.session_state.get("chat_model") != model:
                    init_chat(model)
                
                # Intentar hasta 3 veces por modelo si hay error 503 (sobredemanda)
                success = False
                for attempt in range(3):
                    try:
                        response = st.session_state.chat.send_message(prompt)
                        response_text = response.text
                        success = True
                        break
                    except Exception as e:
                        err_msg = str(e)
                        if ("503" in err_msg or "UNAVAILABLE" in err_msg) and attempt < 2:
                            time.sleep(2 * (attempt + 1))  # Esperar 2s, luego 4s antes de reintentar
                        else:
                            break
                
                if success:
                    break

            if response_text:
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            else:
                st.error("Servidor ocupado temporalmente. Por favor, intenta enviar tu mensaje nuevamente en unos segundos.")