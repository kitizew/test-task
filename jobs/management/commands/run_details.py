import logging
import random
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from jobs.models import Company, Job
from jobs.services.linkedin import fetch_job_details

logger = logging.getLogger(__name__)


def reset_stuck(minutes=15):
    """Вакансії, які завис воркер (впав/перезапустився), повертаємо в чергу."""
    return Job.objects.filter(
        status=Job.Status.PROCESSING,
        updated_at__lt=timezone.now() - timedelta(minutes=minutes),
    ).update(status=Job.Status.NEW)


def claim_batch(size, max_attempts):
    with transaction.atomic():
        ids = list(
            Job.objects.select_for_update(skip_locked=True)
            .filter(status__in=[Job.Status.NEW, Job.Status.FAILED],
                    attempts__lt=max_attempts)
            .order_by("id")
            .values_list("id", flat=True)[:size]
        )
        Job.objects.filter(id__in=ids).update(
            status=Job.Status.PROCESSING, updated_at=timezone.now()
        )
    return ids


class Command(BaseCommand):
    help = "Part 2: добір повних даних (можна запускати в кількох копіях)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--max-attempts", type=int, default=3)
        parser.add_argument("--batch", type=int, default=20)
        parser.add_argument("--loop", action="store_true")

    def handle(self, *args, **o):
        reset_stuck()
        processed = 0
        while True:
            size = o["batch"]
            if o["limit"]:
                size = min(size, o["limit"] - processed)
                if size <= 0:
                    break
            ids = claim_batch(size, o["max_attempts"])
            if not ids:
                if o["loop"]:
                    reset_stuck()
                    time.sleep(60)
                    continue
                break
            for job_id in ids:
                self.handle_one(job_id)
                processed += 1
                time.sleep(random.uniform(1, 3))
        self.stdout.write(self.style.SUCCESS(f"Оброблено: {processed}"))

    def handle_one(self, job_id):
        job = Job.objects.get(pk=job_id)
        try:
            self.process(job)
            self.stdout.write(f"  ✔ {job.linkedin_job_id} {job.title}")
        except Exception as e:
            job.status = Job.Status.FAILED
            job.error = f"{type(e).__name__}: {e}"[:2000]
            job.attempts += 1
            job.save(update_fields=["status", "error", "attempts", "updated_at"])
            logger.error("Вакансія %s: %s", job.linkedin_job_id, e)
            self.stderr.write(f"  ✖ {job.linkedin_job_id}: {e}")

    @transaction.atomic
    def process(self, job):
        data = fetch_job_details(job.linkedin_job_id)
        c = data["company"]
        company = None
        if c["linkedin_id"]:
            company, _ = Company.objects.update_or_create(
                linkedin_id=c["linkedin_id"],
                defaults={"name": c["name"], "url": c["url"]},
            )
        job.title = data["title"]
        job.description = data["description"]
        job.seniority = data["seniority"]
        job.employment_type = data["employment_type"]
        job.job_function = data["job_function"]
        job.industries = data["industries"]
        job.applicants = data["applicants"]
        job.company = company
        job.status = Job.Status.DONE
        job.error = ""
        job.save()