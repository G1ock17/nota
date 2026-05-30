import cloudscraper
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

url = "https://www.fragrantica.com/perfume/Tom-Ford/Noir-de-Noir-1822.html"
print(f"Fetching {url}...")
r = scraper.get(url, timeout=20)
print(f"Status: {r.status_code}, Len: {len(r.text)}")

if r.status_code == 200:
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
        print(f"Description: {text[:300]}")
    else:
        print("No description match")
else:
    print(r.text[:500])
