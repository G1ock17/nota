import requests
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

url = "https://web.archive.org/web/2025/https://www.fragrantica.com/perfume/Tom-Ford/Noir-de-Noir-1822.html"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, allow_redirects=True)
print(f"Status: {r.status_code}, Len: {len(r.text)}, URL: {r.url}")

if "itemprop" in r.text:
    m = re.search(r'itemprop="description"[^>]*>\s*(.*?)\s*</div>', r.text, re.DOTALL)
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
        print(f"Description found: {text[:300]}")
    else:
        print("No itemprop=description match")
else:
    print("No itemprop in page")
