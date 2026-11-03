import json
import requests
from bs4 import BeautifulSoup

slug = "caci-international-inc"
url = f"https://www.linkedin.com/company/{slug}"
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0",
    "Accept-Language": "en-US,en;q=0.9",
}
r = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
print("status:", r.status_code, "| final url:", r.url, "| len:", len(r.text))

soup = BeautifulSoup(r.text, "lxml")
print("title:", soup.title.get_text(strip=True) if soup.title else None)

for s in soup.select('script[type="application/ld+json"]'):
    print("JSON-LD:", s.string[:1500] if s.string else None)

for dt in soup.select('[data-test-id="about-us"] dt'):
    dd = dt.find_next_sibling("dd")
    print(dt.get_text(strip=True), "=", dd.get_text(" ", strip=True) if dd else None)

open("company.html", "w").write(r.text)