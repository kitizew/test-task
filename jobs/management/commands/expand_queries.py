from django.core.management.base import BaseCommand
from django.db.models import Count

from jobs.management.commands.run_search import split_query
from jobs.models import SearchQuery


class Command(BaseCommand):
    help = "Розбиває вже пройдені запити, що впёрлись у ліміт, на дочірні за фільтрами"

    def add_arguments(self, parser):
        parser.add_argument("--threshold", type=int, default=900,
                            help="Мінімум вакансій у запиті, щоб вважати його обрізаним")
        parser.add_argument("--max-depth", type=int, default=3)

    def handle(self, *args, **o):
        qs = (SearchQuery.objects.filter(last_run_at__isnull=False)
              .annotate(n=Count("jobs", distinct=True))
              .filter(n__gte=o["threshold"]))
        total = 0
        for q in qs:
            created = split_query(q, o["max_depth"])
            total += created
            if created:
                self.stdout.write(f"  {q} ({q.n}) -> +{created}")
        self.stdout.write(self.style.SUCCESS(f"Створено дочірніх запитів: {total}"))