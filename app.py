import streamlit as st
import requests
import json
from readability import Document
from bs4 import BeautifulSoup
import os
from PyPDF2 import PdfReader
import io
import logging
from datetime import datetime

# Configure logging (internal, not UI)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# API keys
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
SEARCH_URL = "https://google.serper.dev/search"

# Error if missing keys
if not MISTRAL_API_KEY or not SERPAPI_KEY:
    st.error("API keys not set! Please set MISTRAL_API_KEY and SERPAPI_KEY in your environment variables.")
    st.stop()

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "recent_searches" not in st.session_state:
    st.session_state.recent_searches = []
if "initial_greeting" not in st.session_state:
    # Fetch greeting on app load
    payload = {
        "model": "mistral-tiny",
        "messages": [{"role": "user", "content": "Greet the user briefly and professionally about KRA tax help."}],
        "stream": True
    }
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    response = requests.post(MISTRAL_CHAT_URL, headers=headers, json=payload, stream=True, timeout=10)
    greeting = ""
    for chunk in response.iter_lines():
        if chunk:
            chunk_str = chunk.decode().replace("data: ", "")
            if chunk_str == "[DONE]":
                break
            try:
                data = json.loads(chunk_str)
                if data.get("choices"):
                    greeting += data["choices"][0]["delta"].get("content", "")
            except json.JSONDecodeError:
                continue
    st.session_state.initial_greeting = greeting or "Welcome! I’m here to assist with KRA tax queries."

# Functions for API calls
def get_kra_urls(query):
    search_query = f"{query} site:kra.go.ke"
    payload = json.dumps({"q": search_query})
    headers = {"X-API-KEY": SERPAPI_KEY, "Content-Type": "application/json"}
    response = requests.post(SEARCH_URL, headers=headers, data=payload)
    if not response.ok:
        logger.warning(f"Search API failed for '{query}', using fallback URL")
        return ["https://www.kra.go.ke/helping-tax-payers/faqs/filing-returns-on-itax"]
    results = response.json()
    urls = [item["link"] for item in results.get("organic", []) if "kra.go.ke" in item["link"]][:5]
    logger.info(f"Fetched URLs for '{query}': {urls}")
    return urls

def extract_text_from_urls(urls):
    texts = []
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            if url.lower().endswith(".pdf"):
                pdf_file = io.BytesIO(r.content)
                reader = PdfReader(pdf_file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
                texts.append({"url": url, "content": text[:500]})
                logger.info(f"Extracted PDF text from {url}")
            else:
                doc = Document(r.text)
                readable = BeautifulSoup(doc.summary(), "html.parser").get_text()
                texts.append({"url": url, "content": readable})
                logger.info(f"Extracted HTML text from {url}")
        except requests.exceptions.SSLError as ssl_err:
            try:
                r = requests.get(url, timeout=10, verify=False)
                r.raise_for_status()
                if url.lower().endswith(".pdf"):
                    pdf_file = io.BytesIO(r.content)
                    reader = PdfReader(pdf_file)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() or ""
                    texts.append({"url": url, "content": text[:500]})
                    logger.info(f"Extracted PDF text from {url} (SSL bypassed)")
                else:
                    doc = Document(r.text)
                    readable = BeautifulSoup(doc.summary(), "html.parser").get_text()
                    texts.append({"url": url, "content": readable})
                    logger.info(f"Extracted HTML text from {url} (SSL bypassed)")
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
    return texts

def stream_mistral_response(prompt):
    payload = {
        "model": "mistral-tiny",
        "messages": [
            {"role": "system", "content": "Answer concisely and directly using only the provided KRA text, without prefacing or qualifying the response."},
            {"role": "user", "content": prompt}
        ],
        "stream": True
    }
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    response = requests.post(MISTRAL_CHAT_URL, headers=headers, json=payload, stream=True, timeout=30)
    return response

# Function to save feedback
def save_feedback(query, response, rating):
    feedback_entry = {
        "query": query,
        "response": response,
        "rating": rating,
        "timestamp": datetime.now().isoformat()
    }
    try:
        with open("feedback_log.json", "r") as f:
            feedback_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        feedback_data = []
    
    feedback_data.append(feedback_entry)
    with open("feedback_log.json", "w") as f:
        json.dump(feedback_data, f, indent=2)

# Custom CSS (unchanged)
st.markdown(
    """
    <style>
        body {
            background-color: #1f2937;
            color: #f9fafb;
        }
        .user {
            float: right;
            color: black;
            font-family: Georgia;
            font-weight: bold;
            background-color: rgba(211, 211, 211, 0.5);
            padding: 5px;
            border-radius: 5px;
            display: inline-block;
        }
        .bot {
            float: left;
            color: #f9fafb;
            font-family: Georgia;
            clear: both;
        }
        .chat-container {
            max-height: 400px;
            overflow-y: auto;
            padding: 10px;
            border: 1px solid #4b5563;
            border-radius: 10px;
            background-color: #374151;
        }
        .sidebar .sidebar-content .topic-button {
            background-color: #4CAF50;
            color: white;
            padding: 8px;
            margin: 4px 0;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            width: 100%;
            text-align: left;
        }
        .sidebar .sidebar-content .topic-button:hover {
            background-color: #45a049;
        }
        .stTextInput > div > div > input {
            background-color: #4b5563;
            color: #f9fafb;
            border: 1px solid #6b7280;
        }
        .stButton > button {
            background-color: #3b82f6;
            color: white;
            border-radius: 5px;
        }
        .stButton > button:hover {
            background-color: #2563eb;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# Sidebar (unchanged)
with st.sidebar:
    st.header("KRA Tax Assistant")
    st.markdown("Your guide to KRA tax policies and procedures.")
    
    for search in st.session_state.recent_searches[-5:]:
        if st.button(search, key=f"recent_{search}", help=f"Revisit: {search}", use_container_width=True):
            st.session_state.user_input = search
            st.rerun()
    
    st.markdown("**KRA Resources**")
    st.markdown("- [KRA Website](https://www.kra.go.ke/)")
    st.markdown("- [iTax Portal](https://itax.kra.go.ke/)")
    st.markdown("- [Contact KRA](https://www.kra.go.ke/contact-us)")

# Streamlit UI
st.title("🇰🇪 KRA Tax Assistant")
st.write("Ask a question below, and I’ll help with KRA tax information.")

# Chat display with feedback buttons
chat_container = st.container()
with chat_container:
    st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
    # Show initial greeting
    st.markdown(f"<p class='bot'>{st.session_state.initial_greeting}</p>", unsafe_allow_html=True)
    for i, entry in enumerate(st.session_state.chat_history):
        if entry['user']:
            st.markdown(f"<p class='user'>{entry['user']}</p>", unsafe_allow_html=True)
        bot_response = entry['bot'].replace('\n', '<br>').replace('\t', '    ')
        st.markdown(f"<p class='bot'>{bot_response}</p>", unsafe_allow_html=True)
        if entry['user']:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("👍", key=f"up_{i}", help="Good response"):
                    save_feedback(entry['user'], entry['bot'], "positive")
                    st.write("Thanks for the feedback!")
            with col2:
                if st.button("👎", key=f"down_{i}", help="Bad response"):
                    save_feedback(entry['user'], entry['bot'], "negative")
                    st.write("Sorry, we’ll work on improving this!")
    st.markdown("</div>", unsafe_allow_html=True)

# User input
def process_query():
    query = st.session_state.user_input
    if query and not any(entry['user'] == query for entry in st.session_state.chat_history):
        with st.spinner("Fetching answer..."):
            urls = get_kra_urls(query)
            content_blocks = extract_text_from_urls(urls)

        if not content_blocks:
            response = "I didn’t find enough info—please rephrase your question or try again."
        else:
            combined_text = "".join([block["content"] for block in content_blocks])[:12000]
            prompt_intro = f"{query} Provide a clear and concise answer based solely on the information from the fetched Kenya Revenue Authority (KRA) pages below:"
            full_prompt = f"{prompt_intro}\n\n{combined_text}"

            response_stream = stream_mistral_response(full_prompt)
            answer_text = ""
            for chunk in response_stream.iter_lines():
                if chunk:
                    chunk_str = chunk.decode().replace("data: ", "")
                    if chunk_str == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk_str)
                        if data.get("choices"):
                            token = data["choices"][0]["delta"].get("content", "")
                            answer_text += token
                    except json.JSONDecodeError:
                        continue

            source_links = ", ".join([f'<a href="{block["url"]}" target="_blank">{block["url"]}</a>' for block in content_blocks])
            response = f"{answer_text}<br><br>**Sources:** {source_links}"

        st.session_state.chat_history.append({"user": query, "bot": response})
        if query not in st.session_state.recent_searches:
            st.session_state.recent_searches.append(query)
    st.session_state.user_input = ""

st.text_input("Ask your question here:", key="user_input", value="", on_change=process_query)
