import streamlit as st
import requests
import json
from readability import Document
from bs4 import BeautifulSoup
import os

# API keys
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "QlLF9qhUP5dhDVGH8Pe3PteDZxPcZh4m")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "fee765e7e70c1e59ac2d2e68b0b50f0d633c3ccd")
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
SEARCH_URL = "https://google.serper.dev/search"

# Error if missing keys
if not MISTRAL_API_KEY or not SERPAPI_KEY:
    st.error("API keys not set!")
    st.stop()

def get_kra_urls(query):
    search_query = f"{query} site:kra.go.ke"
    payload = json.dumps({"q": search_query})
    headers = {"X-API-KEY": SERPAPI_KEY, "Content-Type": "application/json"}
    response = requests.post(SEARCH_URL, headers=headers, data=payload)

    if not response.ok:
        return ["https://www.kra.go.ke/helping-tax-payers/faqs/filing-returns-on-itax"]
    
    results = response.json()
    return [item["link"] for item in results.get("organic", []) if "kra.go.ke" in item["link"]][:5]

def extract_text_from_urls(urls):
    texts = []
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            doc = Document(r.text)
            readable = BeautifulSoup(doc.summary(), "html.parser").get_text()
            texts.append(f"Source: {url}\n{readable}\n\n")
        except Exception as e:
            st.warning(f"Could not fetch {url}: {e}")
    return texts



def stream_mistral_response(prompt):
    payload = {
        "model": "mistral-tiny",
        "messages": [
            {"role": "system", "content": "You are a precise assistant that answers based only on the provided KRA text. Avoid external knowledge, speculation, or disclaimers about missing info."},
            {"role": "user", "content": prompt}
        ],
        "stream": True
    }
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    response = requests.post(MISTRAL_CHAT_URL, headers=headers, json=payload, stream=True, timeout=30)
    return response

# Streamlit UI
st.title("🇰🇪 KRA Tax Answer Assistant")
user_input = st.text_input("Ask a KRA-related question (e.g. 'What is VAT?')")

if user_input:
    if not user_input.endswith("?") and not any(w in user_input.lower() for w in ["what", "how", "who", "can"]):
        st.warning("That doesn't look like a question.")
    else:
        with st.spinner("Searching KRA..."):
            urls = get_kra_urls(user_input)
            content_blocks = extract_text_from_urls(urls)

        if not content_blocks:
            st.error("Could not extract any text from KRA pages.")
        else:
            combined_text = "".join(content_blocks)[:12000]  # Keep it within token limits
            prompt_intro = f"{user_input} Provide a clear and concise answer based solely on the information from the fetched Kenya Revenue Authority (KRA) pages below. Do not express doubt or speculate beyond this content:"
            full_prompt = f"{prompt_intro}\n\n{combined_text}"

            st.subheader("📢 Answer")
            response = stream_mistral_response(full_prompt)
            answer_box = st.empty()
            answer_text = ""

            for chunk in response.iter_lines():
                if chunk:
                    chunk_str = chunk.decode().replace("data: ", "")
                    if chunk_str == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk_str)
                        if data.get("choices"):
                            token = data["choices"][0]["delta"].get("content", "")
                            answer_text += token
                            answer_box.markdown(answer_text)
                    except json.JSONDecodeError:
                        continue

            st.subheader("🔗 Sources")
            for url in urls:
                st.markdown(f"- [KRA Source]({url})")

