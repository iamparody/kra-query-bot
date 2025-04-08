import os
import requests
import json
from readability import Document
from bs4 import BeautifulSoup

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
MISTRAL_CHAT_URL = "https://api.mixtral.ai/v1/chat/completions"  # Adjust if needed
SEARCH_URL = "https://google.serper.dev/search"

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

def handler(request):
    if request.method != "POST":
        return {"error": "Use POST"}, 405
    msg = request.get_json().get("message", "")
    if not msg:
        return {"error": "No message provided"}, 400

    urls = get_news_urls(msg)
    texts = get_cleaned_text(urls)
    combined_text = "".join(texts)[:2000]
    prompt = f"{msg} Answer based on KRA data:\n\n{combined_text}"
    payload = {
        "model": "mistral-tiny",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(MISTRAL_CHAT_URL, headers=headers, json=payload, timeout=8)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return {"answer": content, "sources": urls}, 200
    except Exception as e:
        return {"error": str(e)}, 500

from http.server import BaseHTTPRequestHandler
from json import dumps
class VercelHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        request = type('Request', (), {'method': 'POST', 'get_json': lambda: json.loads(post_data.decode())})
        response, status = handler(request)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(dumps(response).encode())

def vercel_app(request):
    return VercelHandler(request, None, None)
