import logging
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAILS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

session = requests.Session()
session.headers.update(HEADERS)


class RetryableError(Exception):
    """429 / 5xx: має сенс спробувати ще раз."""


class NotFoundError(Exception):
    """Вакансію видалено або вона недоступна."""


@retry(
    retry=retry_if_exception_type(
        (RetryableError, requests.exceptions.ConnectionError, requests.exceptions.Timeout)
    ),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    reraise=True,
)
def _get(url, params=None):
    r = session.get(url, params=params, timeout=20)
    if r.status_code == 429 or r.status_code >= 500:
        raise RetryableError(f"HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError(url)
    r.raise_for_status()
    return r.text


def company_slug(url):
    if not url:
        return ""
    return urlparse(url).path.rstrip("/").split("/")[-1]


def clean_url(url):
    """Прибирає ?trk=... та інші параметри."""
    if not url:
        return ""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def fetch_search_page(keywords, location, start=0):
    """Повертає список словників з базовими даними вакансій."""
    html = _get(SEARCH_URL, params={"keywords": keywords, "location": location, "start": start})
    soup = BeautifulSoup(html, "lxml")

    results = []
    for card in soup.select("div.base-card"):
        urn = card.get("data-entity-urn", "")
        job_id = urn.split(":")[-1] if urn else ""
        if not job_id:
            continue

        title = card.select_one("h3.base-search-card__title")
        company = card.select_one("h4.base-search-card__subtitle a")
        location_el = card.select_one("span.job-search-card__location")
        link = card.select_one("a.base-card__full-link")
        posted = card.select_one("time")

        results.append({
            "job_id": job_id,
            "title": title.get_text(strip=True) if title else "",
            "company_name": company.get_text(strip=True) if company else "",
            "company_url": clean_url(company.get("href")) if company else "",
            "location": location_el.get_text(strip=True) if location_el else "",
            "url": clean_url(link.get("href")) if link else "",
            "posted_at": posted.get("datetime") if posted else None,
        })
    return results


def fetch_job_details(job_id):
    """Повертає словник з повними даними вакансії та компанії."""
    html = _get(DETAILS_URL.format(job_id=job_id))
    soup = BeautifulSoup(html, "lxml")

    def text(sel):
        el = soup.select_one(sel)
        return el.get_text(" ", strip=True) if el else ""

    criteria = {}
    for li in soup.select("li.description__job-criteria-item"):
        k = li.select_one("h3")
        v = li.select_one("span")
        if k and v:
            criteria[k.get_text(strip=True)] = v.get_text(strip=True)

    company_link = soup.select_one("a.topcard__org-name-link")
    company_url = clean_url(company_link.get("href")) if company_link else ""

    description = text("div.show-more-less-html__markup")
    title = text("h2.top-card-layout__title")
    if not title or not description:
        raise ValueError(f"Не вдалося розпарсити вакансію {job_id}")

    return {
        "title": title,
        "description": description,
        "seniority": criteria.get("Seniority level", ""),
        "employment_type": criteria.get("Employment type", ""),
        "job_function": criteria.get("Job function", ""),
        "industries": criteria.get("Industries", ""),
        "applicants": text("span.num-applicants__caption"),
        "company": {
            "linkedin_id": company_slug(company_url),
            "name": company_link.get_text(strip=True) if company_link else "",
            "url": company_url,
        },
    }