import requests
from bs4 import BeautifulSoup

from urllib.parse import urlparse

def company_slug(url):
    path = urlparse(url).path        
    return path.rstrip("/").split("/")[-1]

job_id = "4431992044"
url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0",
    "Accept-Language": "en-US,en;q=0.9",
}

r = requests.get(url, headers=headers, timeout=20)
print(r.status_code)
soup = BeautifulSoup(r.text, "lxml")

def text(sel):
    el = soup.select_one(sel)
    return el.get_text(" ", strip=True) if el else None

print("title:", text("h2.top-card-layout__title"))
print("company:", text("a.topcard__org-name-link"))
link = soup.select_one("a.topcard__org-name-link")
print("company url:", link.get("href") if link else None)
print("description:", (text("div.show-more-less-html__markup") or "")[:300])

criteria = {}
for li in soup.select("li.description__job-criteria-item"):
    k = li.select_one("h3")
    v = li.select_one("span")
    if k and v:
        criteria[k.get_text(strip=True)] = v.get_text(strip=True)

seniority = criteria.get("Seniority level", "")
employment_type = criteria.get("Employment type", "")
job_function = criteria.get("Job function", "")
industries = criteria.get("Industries", "")

print("slug:", company_slug(link.get("href")) if link else None)
print("seniority:", seniority)
print("employment_type:", employment_type)
print("job_function:", job_function)
print("industries:", industries)