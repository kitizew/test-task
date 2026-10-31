import logging
import random
import time

from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import Company, Job
from jobs.services.linkedin import fetch_job_details

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Part 2: добір повних даних по вакансіях (NEW / FAILED)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0,
                            help="Скільки вакансій обробити (0 = усі)")
        parser.add_argument("--max-attempts", type=int, default=3)

    def handle(self, *args, **options):
        jobs = Job.objects.filter(
            status__in=[Job.Status.NEW, Job.Status.FAILED],
            attempts__lt=options["max_attempts"],
        ).order_by("id")

        if options["limit"]:
            jobs = jobs[: options["limit"]]

        done = failed = 0
        for job in jobs:
            try:
                self.process(job)
                done += 1
                self.stdout.write(f"  ✔ {job.linkedin_job_id} {job.title}")
            except Exception as e:
                failed += 1
                job.status = Job.Status.FAILED
                job.error = f"{type(e).__name__}: {e}"[:2000]
                job.attempts += 1
                job.save(update_fields=["status", "error", "attempts", "updated_at"])
                logger.exception("Вакансія %s", job.linkedin_job_id)
                self.stderr.write(f"  ✖ {job.linkedin_job_id}: {e}")
            time.sleep(random.uniform(1, 3))

        self.stdout.write(self.style.SUCCESS(f"Готово: {done} ок, {failed} помилок"))

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