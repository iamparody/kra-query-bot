import chainlit as cl
import requests
import json
from readability import Document
from bs4 import BeautifulSoup
import os

#MISTRAL_API_KEY = "QlLF9qhUP5dhDVGH8Pe3PteDZxPcZh4m"  # Or use os.environ
#SERPAPI_KEY = "fee765e7e70c1e59ac2d2e68b0b50f0d633c3ccd"
#MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
#SEARCH_URL = "https://google.serper.dev/search"
port = int(os.environ.get("PORT", 10000))  # Render sets $PORT, default 10000 locally

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "QlLF9qhUP5dhDVGH8Pe3PteDZxPcZh4m")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "fee765e7e70c1e59ac2d2e68b0b50f0d633c3ccd")
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
SEARCH_URL = "https://google.serper.dev/search"
if not MISTRAL_API_KEY or not SERPAPI_KEY:
    raise ValueError("API keys not set in environment variables.")

def get_news_urls(query):
    print(f"Fetching URLs for query: {query}")
    search_query = f"{query} site:kra.go.ke"
    payload = json.dumps({"q": search_query})
    headers = {"X-API-KEY": SERPAPI_KEY, "Content-Type": "application/json"}
    response = requests.post(SEARCH_URL, headers=headers, data=payload)
    if not response.ok:
        print(f"SerpAPI error: {response.status_code} - {response.text}")
        return ["https://www.kra.go.ke/helping-tax-payers/faqs/filing-returns-on-itax"]
    search_results = response.json()
    urls = [result["link"] for result in search_results.get("organic", []) 
            if result["link"].startswith("https://www.kra.go.ke/")][:10]
    print(f"URLs fetched: {urls}")
    return urls if urls else ["https://www.kra.go.ke/helping-tax-payers/faqs/filing-returns-on-itax"]

def get_cleaned_text(urls):
    texts = []
    for url in urls:
        print(f"Fetching content from: {url}")
        try:
            response = requests.get(url, timeout=10)
            html = response.text
            doc = Document(html)
            text = BeautifulSoup(doc.summary(), "html.parser").get_text()
            texts.append(f"Source: {url}\n{text}\n\n")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
    print(f"Text extracted, length: {len(''.join(texts))} chars")
    return texts

@cl.on_chat_start
async def start():
    await cl.Message(content="Hello! Ask me a question about KRA taxes, and I’ll fetch the answer from official sources.").send()

@cl.on_message
async def main(message):
    if isinstance(message, str):
        msg_content = message.strip().lower()
    else:
        msg_content = message.content.strip().lower()
    if not (msg_content.endswith("?") or "what" in msg_content or "how" in msg_content or "who" in msg_content or "can" in msg_content):
        await cl.Message(content="That’s not a question! Try asking something like 'What is the VAT rate?'").send()
        return

    loading_msg = cl.Message(content="Fetching answer...")
    await loading_msg.send()

    urls = get_news_urls(message if isinstance(message, str) else message.content)
    texts = get_cleaned_text(urls)
    
    max_chars = 30000 - 1000
    combined_text = "".join(texts)[:max_chars]
    prompt_intro = f"{message if isinstance(message, str) else message.content} Provide a clear and concise answer based solely on the information from the fetched Kenya Revenue Authority (KRA) pages below. Do not express doubt or speculate beyond this content:"
    prompt = f"{prompt_intro}\n\n{combined_text}"
    print(f"Prompt length: {len(prompt)} chars")

    payload = {
        "model": "mistral-tiny",
        "messages": [
            {"role": "system", "content": "You are a precise assistant that answers based only on the provided KRA text. Avoid external knowledge, speculation, or disclaimers about missing info."},
            {"role": "user", "content": prompt}
        ],
        "stream": True
    }
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}

    print("Sending request to Mistral...")
    try:
        response = requests.post(MISTRAL_CHAT_URL, headers=headers, json=payload, stream=True, timeout=30)
        if not response.ok:
            error_text = response.text
            print(f"Mistral error: {response.status_code} - {error_text}")
            await cl.Message(content=f"Error fetching answer: {error_text}").send()
            await loading_msg.remove()
            return

        msg = cl.Message(content="")
        await msg.send()
        full_content = ""
        for chunk in response.iter_lines():
            if chunk:
                chunk_str = chunk.decode().replace("data: ", "")
                if chunk_str == "[DONE]":
                    continue
                try:
                    data = json.loads(chunk_str)
                    if data.get("choices"):
                        content = data["choices"][0]["delta"].get("content", "")
                        full_content += content
                        await msg.stream_token(content)
                except json.JSONDecodeError:
                    print(f"Skipping malformed chunk: {chunk_str}")
                    continue
        msg.content = f"{full_content}\n\n**Sources:**\n" + '\n'.join(urls)
        await msg.send()
        await loading_msg.remove()
    except Exception as e:
        print(f"Unexpected error: {e}")
        error_msg = cl.Message(content=f"An error occurred: {str(e)}")
        await error_msg.send()
        await loading_msg.remove()

if __name__ == "__main__":
    import chainlit.cli as cli
    import sys

    sys.argv = ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", str(port)]
    cli.main()
