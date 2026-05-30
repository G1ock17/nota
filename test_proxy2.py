import requests
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

proxy_url = "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&protocol=http&timeout=5000&anonymity=elite,anonymous&country=de,nl,fr,us,gb"
print("Fetching proxy list...")
r = requests.get(proxy_url, timeout=10)
proxies = [p.strip() for p in r.text.strip().split("\n") if p.strip()]
print(f"Found {len(proxies)} proxies")

target = "https://www.fragrantica.com/perfume/Tom-Ford/Noir-de-Noir-1822.html"

for i, proxy in enumerate(proxies[:15]):
    try:
        pr = requests.get(
            target,
            proxies={"http": proxy, "https": proxy},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=10,
        )
        print(f"[{i}] {proxy} -> {pr.status_code}")
        if pr.status_code == 200 and "itemprop" in pr.text:
            m = re.search(r'itemprop="description"[^>]*>\s*(.*?)\s*</div>', pr.text, re.DOTALL)
            if m:
                text = re.sub(r"<[^>]+>", "", m.group(1))
                text = re.sub(r"\s+", " ", text).strip()[:150]
                print(f"  DESC: {text}")
                break
    except Exception as e:
        print(f"[{i}] {proxy} -> ERR: {type(e).__name__}")
