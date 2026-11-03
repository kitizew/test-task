import csv

from django.core.management.base import BaseCommand

from jobs.models import Job

FIELDS = [
    "linkedin_job_id", "title", "location", "url", "posted_at", "seniority",
    "employment_type", "job_function", "industries", "applicants", "status",
    "description",
]
COMPANY_FIELDS = ["linkedin_id", "name", "url", "website", "industry", "size",
                  "headquarters", "description", "company_type", "founded",
                  "specialties", "logo_url"]


class Command(BaseCommand):
    help = "Експорт вакансій і компаній у CSV"

    def add_arguments(self, parser):
        parser.add_argument("--output", default="jobs_export.csv")

    def handle(self, *args, **options):
        header = FIELDS + [f"company_{f}" for f in COMPANY_FIELDS]
        qs = Job.objects.select_related("company").order_by("id")

        with open(options["output"], "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(header)
            for j in qs.iterator():
                row = [getattr(j, x) for x in FIELDS]
                c = j.company
                row += [getattr(c, x) if c else "" for x in COMPANY_FIELDS]
                w.writerow(row)

        self.stdout.write(self.style.SUCCESS(f"Збережено {qs.count()} → {options['output']}"))