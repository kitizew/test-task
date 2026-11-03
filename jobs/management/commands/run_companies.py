import logging
import random
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from jobs.models import Company
from jobs.services.linkedin import BlockedError, fetch_company_details

logger = logging.getLogger(__name__)
S = Company.DetailsStatus
FIELDS = ["description", "headquarters", "logo_url", "website", "industry",
          "size", "company_type", "founded", "specialties"]


def reset_stuck(minutes=15):
    Company.objects.filter(
        details_status=S.PROCESSING,
        details_updated_at__lt=timezone.now() - timedelta(minutes=minutes),
    ).update(details_status=S.NEW)


def claim_batch(size, max_attempts):
    with transaction.atomic():
        ids = list(
            Company.objects.select_for_update(skip_locked=True)
            .filter(details_status__in=[S.NEW, S.FAILED],
                    details_attempts__lt=max_attempts)
            .order_by("id").values_list("id", flat=True)[:size]
        )
        Company.objects.filter(id__in=ids).update(
            details_status=S.PROCESSING, details_updated_at=timezone.now())
    return ids


class Command(BaseCommand):
    help = "Part 3: добір даних про компанії"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--max-attempts", type=int, default=3)
        parser.add_argument("--batch", type=int, default=10)
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
            for cid in ids:
                blocked = self.handle_one(cid)
                processed += 1
                time.sleep(random.uniform(30, 60) if blocked else random.uniform(3, 6))
        self.stdout.write(self.style.SUCCESS(f"Оброблено: {processed}"))

    def handle_one(self, cid):
        c = Company.objects.get(pk=cid)
        try:
            data = fetch_company_details(c.linkedin_id)
            for f in FIELDS:
                if data.get(f):
                    setattr(c, f, data[f])
            c.details_status = S.DONE
            c.details_error = ""
            c.details_updated_at = timezone.now()
            c.save()
            self.stdout.write(f"  ✔ {c.name}")
            return False
        except Exception as e:
            c.details_status = S.FAILED
            c.details_attempts += 1
            c.details_error = f"{type(e).__name__}: {e}"[:2000]
            c.details_updated_at = timezone.now()
            c.save(update_fields=["details_status", "details_attempts",
                                  "details_error", "details_updated_at"])
            self.stderr.write(f"  ✖ {c.name}: {e}")
            return isinstance(e, BlockedError)