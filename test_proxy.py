import requests
import re
import json

url = "https://api.allorigins.win/get?url=" + requests.utils.quote(
    "https://www.fragrantica.com/perfume/Tom-Ford/Noir-de-Noir-1822.html"
)
r = requests.get(url, timeout=30)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    content = data.get("contents", "")
    print(f"Content length: {len(content)}")
    m = re.search(
        r'itemprop="description"[^>]*>\s*(.*?)\s*</div>', content, re.DOTALL
    )
    if m:
        block = m.group(1)
        block = re.sub(r"<blockquote[^>]*>.*?</blockquote>", "", block, flags=re.DOTALL)
        block = re.sub(
            r'<div[^>]*class="[^"]*fragrantica-blockquote[^"]*"[^>]*>.*?</div>',
            "", block, flags=re.DOTALL,
        )
        text = re.sub(r"<[^>]+>", "", block)
        text = text.replace("&amp;", "&").replace("&#039;", "'").replace("&quot;", '"')
        text = re.sub(r"\s+", " ", text).strip()
        print(f"Description: {text[:300]}")
    else:
        print("No description found")
