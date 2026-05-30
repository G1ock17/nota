import httpx
import sys

sys.stdout.reconfigure(encoding="utf-8")

client = httpx.Client(
    http2=True,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    follow_redirects=True,
    timeout=20,
)

r = client.get("https://www.fragrantica.com/perfume/Tom-Ford/Noir-de-Noir-1822.html")
print(f"Status: {r.status_code}, HTTP version: {r.http_version}")
print(f"Content length: {len(r.text)}")
if "itemprop" in r.text:
    print("Has itemprop!")
