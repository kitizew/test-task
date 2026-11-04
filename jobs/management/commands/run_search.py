import logging
import random
import time
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode

import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from jobs.models import Job, SearchQuery
from jobs.services.linkedin import RetryableError, fetch_search_page

logger = logging.getLogger(__name__)

# Порядок вимірів: спочатку ті, що ділять видачу на непересічні частини.
# Значення звір із DevTools (Network -> seeMoreJobPostings/search).
SPLIT_DIMENSIONS = [
    ("f_TPR", ["r86400", "r259200", "r604800", "r1209600", "r2592000"]),
]
SATURATION = 0.9  # частка від max_start, після якої запит вважається обрізаним


def parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def split_query(query, max_depth):
    """Створює дочірні запити за першим вільним виміром. Повертає кількість нових."""
    current = dict(parse_qsl(query.filters))
    if len(current) >= max_depth:
        return 0
    for key, values in SPLIT_DIMENSIONS:
        if key in current:
            continue
        existing = set(
            SearchQuery.objects.filter(keywords=query.keywords, country=query.country)
            .values_list("filters", flat=True)
        )
        children = []
        for v in values:
            f = urlencode({**current, key: v})
            if f not in existing:
                children.append(SearchQuery(keywords=query.keywords,
                                            country=query.country, filters=f))
        SearchQuery.objects.bulk_create(children, ignore_conflicts=True)
        return len(children)
    return 0


def claim_query():
    now = timezone.now()
    with transaction.atomic():
        q = (
            SearchQuery.objects.select_for_update(skip_locked=True)
            .filter(is_active=True, last_run_at__isnull=True)
            .filter(Q(locked_at__isnull=True) | Q(locked_at__lt=now - timedelta(hours=2)))
            .order_by("id")
            .first()
        )
        if q:
            q.locked_at = now
            q.save(update_fields=["locked_at"])
    return q


class Command(BaseCommand):
    help = "Part 1: пошук вакансій і збереження в БД (статус NEW)"

    def add_arguments(self, parser):
        parser.add_argument("--query-id", type=int)
        parser.add_argument("--max-start", type=int, default=1000)
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--no-split", action="store_true",
                            help="Не розбивати обрізані запити автоматично")
        parser.add_argument("--max-depth", type=int, default=3,
                            help="Максимум фільтрів в одному запиті")

    def handle(self, *args, **options):
        if options["query_id"]:
            for q in SearchQuery.objects.filter(pk=options["query_id"]):
                self.run_query(q, options)
            return

        while True:
            q = claim_query()
            if q:
                self.run_query(q, options)
            elif options["loop"]:
                time.sleep(60)
            else:
                self.stdout.write("Немає запитів у черзі.")
                break

    def run_query(self, query, options):
        max_start = options["max_start"]
        self.stdout.write(f"▶ {query}")
        start = 0
        fetched = 0
        total_new = 0
        extra = dict(parse_qsl(query.filters))

        while start < max_start:
            try:
                cards = fetch_search_page(query.keywords, query.country, start, extra)
            except (RetryableError, requests.exceptions.RequestException) as e:
                logger.error("Запит %s, start=%s: %s", query, start, e)
                self.stderr.write(f"  ✖ помилка на start={start}: {e}. Переходжу далі.")
                break

            if not cards:
                self.stdout.write("  вакансії закінчились")
                break

            ids = [c["job_id"] for c in cards]
            before = Job.objects.filter(linkedin_job_id__in=ids).count()

            Job.objects.bulk_create(
                [
                    Job(
                        linkedin_job_id=c["job_id"],
                        title=c["title"],
                        location=c["location"],
                        url=c["url"],
                        posted_at=parse_date(c["posted_at"]),
                    )
                    for c in cards
                ],
                ignore_conflicts=True,
            )

            jobs = Job.objects.filter(linkedin_job_id__in=ids)
            query.jobs.add(*jobs)

            new = jobs.count() - before
            total_new += new
            fetched += len(cards)
            self.stdout.write(f"  start={start}: {len(cards)} карток, нових {new}")

            start += len(cards)
            time.sleep(random.uniform(1, 3))

        created = 0
        if not options["no_split"] and fetched >= max_start * SATURATION:
            created = split_query(query, options["max_depth"])
            self.stdout.write(f"  ⚡ запит обрізаний ({fetched} карток), створено дочірніх: {created}")

        query.last_run_at = timezone.now()
        query.locked_at = None
        query.save(update_fields=["last_run_at", "locked_at"])
        self.stdout.write(self.style.SUCCESS(f"✔ {query}: нових вакансій {total_new}"))