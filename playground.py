import requests
from bs4 import BeautifulSoup
import time

url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


for start in range(0, 30, 10):
    params = {
        "keywords": "Python Developer", 
        "location": "United States", 
        "start": start
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        
        if r.status_code != 200:
            print(f"Помилка {r.status_code}: LinkedIn міг заблокувати запит.")
            break
            
        soup = BeautifulSoup(r.text, "lxml")
        cards = soup.select("div.base-card")
        
        if not cards:
            print("Більше немає вакансій.")
            break
            
        for card in cards:
            urn = card.get("data-entity-urn", "")
            job_id = urn.split(":")[-1] if urn else "N/A"
            
            
            title_elem = card.select_one("h3.base-search-card__title")
            title = title_elem.get_text(strip=True) if title_elem else "N/A"
            
            company_elem = card.select_one("h4.base-search-card__subtitle a")
            company = company_elem.get_text(strip=True) if company_elem else "N/A"
            
            
            location_elem = card.select_one("span.job-search-card__location")
            location = location_elem.get_text(strip=True) if location_elem else "N/A"

            print(f"{job_id} | {title} | {company} | {location}")
            
        time.sleep(2)
        
    except requests.exceptions.RequestException as e:
        print(f"Помилка мережі: {e}")
        break