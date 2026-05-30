import re
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

sys.stdout.reconfigure(encoding="utf-8")

options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])

driver = webdriver.Chrome(options=options)
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
})

url = "https://www.fragrantica.com/perfume/Tom-Ford/Noir-de-Noir-1822.html"
print(f"Fetching {url}...")
driver.get(url)
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
    print(f"Description: {text[:300]}")
else:
    print("No description found")

driver.quit()
