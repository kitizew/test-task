import logging
import random
import time
from datetime import date

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import Job, SearchQuery
from jobs.services.linkedin import RetryableError, fetch_search_page

logger = logging.getLogger(__name__)


def parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Part 1: пошук вакансій і збереження в БД (статус NEW)"

    def add_arguments(self, parser):
        parser.add_argument("--query-id", type=int, help="Запустити лише один SearchQuery")
        parser.add_argument("--max-start", type=int, default=1000,
                            help="Ліміт зміщення (LinkedIn віддає ~1000 на запит)")

    def handle(self, *args, **options):
        queries = SearchQuery.objects.filter(is_active=True)
        if options["query_id"]:
            queries = queries.filter(pk=options["query_id"])

        if not queries.exists():
            self.stdout.write("Немає активних пошукових запитів.")
            return

        for query in queries:
            self.run_query(query, options["max_start"])

    def run_query(self, query, max_start):
        self.stdout.write(f"▶ {query}")
        start = 0
        total_new = 0

        while start < max_start:
            try:
                cards = fetch_search_page(query.keywords, query.country, start)
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
            self.stdout.write(f"  start={start}: {len(cards)} карток, нових {new}")

            start += len(cards)
            time.sleep(random.uniform(1, 3))

        query.last_run_at = timezone.now()
        query.save(update_fields=["last_run_at"])
        self.stdout.write(self.style.SUCCESS(f"✔ {query}: нових вакансій {total_new}"))