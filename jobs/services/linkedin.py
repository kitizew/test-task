import logging
from urllib.parse import parse_qs, unquote, urlparse
import html

import requests
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import os
proxy = os.environ.get("PROXY_URL")
if proxy:
    session.proxies.update({"http": proxy, "https": proxy})

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


class BlockedError(Exception):
    """LinkedIn віддав 999 / authwall."""


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


def fetch_search_page(keywords, location, start=0, extra=None):
    """Повертає список словників з базовими даними вакансій."""
    params = {"keywords": keywords, "location": location, "start": start}
    params.update(extra or {})
    html = _get(SEARCH_URL, params=params)
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

COMPANY_URL = "https://www.linkedin.com/company/{slug}"


def real_url(href):
    """Якщо посилання йде через редірект LinkedIn, дістає справжню адресу."""
    q = parse_qs(urlparse(href).query)
    return unquote(q["url"][0]) if "url" in q else href


def fetch_company_details(slug):
    r = requests.get(COMPANY_URL.format(slug=slug), headers=HEADERS, timeout=20,
                     proxies=session.proxies or None)
    if r.status_code in (999, 429) or "authwall" in r.url:
        raise BlockedError(f"HTTP {r.status_code} {r.url}")
    if r.status_code == 404:
        raise NotFoundError(slug)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    about = {}
    website = ""
    for dt in soup.select('[data-test-id="about-us"] dt'):
        key = dt.get_text(strip=True).lower()
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        about[key] = dd.get_text(" ", strip=True)
        if key == "website":
            a = dd.find("a")
            if a and a.get("href"):
                website = real_url(a["href"])

    meta_desc = soup.select_one('meta[name="description"]')
    og_image = soup.select_one('meta[property="og:image"]')

    out = {
        "website": website,
        "industry": about.get("industry", ""),
        "size": about.get("company size", ""),
        "headquarters": about.get("headquarters", ""),
        "company_type": about.get("type", ""),
        "founded": about.get("founded", ""),
        "specialties": about.get("specialties", ""),
        "description": html.unescape(meta_desc.get("content", "")) if meta_desc else "",
        "logo_url": og_image.get("content", "") if og_image else "",
    }

    if not (out["industry"] or out["size"] or out["website"]):
        raise ValueError(f"Нічого не розпарсилось для {slug}")
    return out