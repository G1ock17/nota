import re
import sys
import time
import undetected_chromedriver as uc

sys.stdout.reconfigure(encoding="utf-8")

options = uc.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")

driver = uc.Chrome(options=options)

url = "https://www.fragrantica.com/perfume/Tom-Ford/Noir-de-Noir-1822.html"
print(f"Fetching {url}...")
driver.get(url)
time.sleep(5)
print(f"Title: {driver.title}")

html = driver.page_source
m = re.search(r'itemprop="description"[^>]*>\s*(.*?)\s*</div>', html, re.DOTALL)
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
    print(f"OK: {text[:300]}")
else:
    print("No description found")
    if "403" in driver.title or "Forbidden" in html[:1000]:
        print("-> 403 Forbidden")
    elif "moment" in driver.title.lower() or "moment" in html[:1000].lower():
        print("-> Cloudflare challenge")

driver.quit()
