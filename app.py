import streamlit as st
import requests
import json
import os
from readability import Document
from bs4 import BeautifulSoup

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "QlLF9qhUP5dhDVGH8Pe3PteDZxPcZh4m")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "fee765e7e70c1e59ac2d2e68b0b50f0d633c3ccd")
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
SEARCH_URL = "https://google.serper.dev/search"
if not MISTRAL_API_KEY or not SERPAPI_KEY:
    raise ValueError("API keys not set in environment variables.")

def get_news_urls(query):
    search_query = f"{query} site:kra.go.ke"
    payload = json.dumps({"q": search_query})
    headers = {"X-API-KEY": SERPAPI_KEY, "Content-Type": "application/json"}
    response = requests.post(SEARCH_URL, headers=headers, data=payload)
    if not response.ok:
        return ["https://www.kra.go.ke/helping-tax-payers/faqs"]
    search_results = response.json()
    return [result["link"] for result in search_results.get("organic", []) if "kra.go.ke" in result["link"]][:5]

def get_cleaned_text(urls):
    texts = []
    for url in urls:
        try:
            response = requests.get(url, timeout=5)
            doc = Document(response.text)
            text = BeautifulSoup(doc.summary(), "html.parser").get_text()
            texts.append(text[:500])
        except:
            continue
    return texts

def get_answer(query):
    urls = get_news_urls(query)
    texts = get_cleaned_text(urls)
    combined_text = "".join(texts)[:2000]
    prompt = f"{query} Answer based on KRA data:\n\n{combined_text}"
    payload = {
        "model": "mistral-tiny",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(MISTRAL_CHAT_URL, headers=headers, json=payload, timeout=8)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"], urls
    except Exception as e:
        return f"Error: {str(e)}", urls

st.title("KRA Query Bot")
query = st.text_input("Ask a question (e.g., What is the tax rate for MRI?):")
if st.button("Get Answer"):
    with st.spinner("Fetching answer..."):
        answer, sources = get_answer(query)
        st.write("**Answer:**", answer)
        st.write("**Sources:**")
        for url in sources:
            st.write(f"- {url}")
