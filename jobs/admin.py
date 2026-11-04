from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.db.models import Min
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Company, Job, SearchQuery



FILTER_LABELS = {
    "f_TPR=r86400": "1д",
    "f_TPR=r259200": "3д",
    "f_TPR=r604800": "7д",
    "f_TPR=r1209600": "14д",
    "f_TPR=r2592000": "30д",
}


class BulkForm(forms.Form):
    keywords = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 8, "cols": 60}),
        help_text="Одна фраза на рядок: Python Developer, Django Developer...",
    )
    locations = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 12, "cols": 60}),
        help_text="Одна локація на рядок: United States, Austin, Texas, United States...",
    )
    filters = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 8, "cols": 60}),
        help_text="Одна комбінація фільтрів на рядок, напр. f_E=2&f_WT=2. "
                  "Рядок «-» означає без фільтрів. Порожнє поле = без фільтрів.",
    )    


def lines(text):
    return list(dict.fromkeys(l.strip() for l in text.splitlines() if l.strip()))


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    change_list_template = "admin/jobs/searchquery/change_list.html"
    list_display = ("keywords", "places", "queries_count", "vacancies", "processed", "active")
    search_fields = ("keywords", "country")
    ordering = ("keywords", "id")
    list_per_page = 50
    actions = ["run_again", "deactivate", "activate"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        match = getattr(request, "resolver_match", None)
        # у списку показуємо один рядок на назву роботи
        if match and match.url_name == "jobs_searchquery_changelist":
            first_ids = (SearchQuery.objects.values("keywords")
                         .annotate(m=Min("id")).values("m"))
            qs = qs.filter(id__in=first_ids)
        return qs

    @admin.display(description="Міста та фільтри")
    def places(self, obj):
        grouped = {}
        rows = SearchQuery.objects.filter(keywords=obj.keywords).values_list("country", "filters")
        for country, flt in rows:
            short = country.replace(", United States", "") or country
            grouped.setdefault(short, 0)
            if flt:
                grouped[short] += 1
        parts = []
        for place, n in sorted(grouped.items()):
            parts.append(f"{place} (+{n} фільтрів)" if n else place)
        return " · ".join(parts)

    @admin.display(description="Запитів")
    def queries_count(self, obj):
        return SearchQuery.objects.filter(keywords=obj.keywords).count()

    @admin.display(description="Вакансій")
    def vacancies(self, obj):
        return Job.objects.filter(queries__keywords=obj.keywords).distinct().count()

    @admin.display(description="Оброблено")
    def processed(self, obj):
        return (Job.objects.filter(queries__keywords=obj.keywords, status="done")
                .distinct().count())

    @admin.display(description="Активні", boolean=True)
    def active(self, obj):
        return SearchQuery.objects.filter(keywords=obj.keywords, is_active=True).exists()

    # дії діють на ВСІ запити вибраної назви, а не лише на видимий рядок
    @admin.action(description="Запустити пошук ще раз", permissions=["change"])
    def run_again(self, request, queryset):
        kws = list(queryset.values_list("keywords", flat=True))
        n = SearchQuery.objects.filter(keywords__in=kws).update(last_run_at=None, locked_at=None)
        self.message_user(request, f"Поставлено в чергу запитів: {n}")

    @admin.action(description="Вимкнути", permissions=["change"])
    def deactivate(self, request, queryset):
        kws = list(queryset.values_list("keywords", flat=True))
        SearchQuery.objects.filter(keywords__in=kws).update(is_active=False)

    @admin.action(description="Увімкнути", permissions=["change"])
    def activate(self, request, queryset):
        kws = list(queryset.values_list("keywords", flat=True))
        SearchQuery.objects.filter(keywords__in=kws).update(is_active=True)

    def get_urls(self):
        return [
            path("bulk-add/", self.admin_site.admin_view(self.bulk_add),
                 name="jobs_searchquery_bulk_add"),
        ] + super().get_urls()

    # метод bulk_add залиш без змін, як був


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    change_list_template = "admin/jobs/job/change_list.html"
    list_display = ("title", "company", "location", "status", "attempts", "posted_at", "created_at")
    list_filter = ("status", "queries__country", "employment_type", "seniority")
    search_fields = ("title", "company__name", "linkedin_job_id")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("company",)
    date_hierarchy = "created_at"
    list_per_page = 50
    show_full_result_count = False
    actions = ["retry"]

    @admin.action(description="Повторити обробку (status=new)", permissions=["change"])
    def retry(self, request, queryset):
        n = queryset.update(status=Job.Status.NEW, attempts=0, error="")
        self.message_user(request, f"Повернено в чергу: {n}")

    def changelist_view(self, request, extra_context=None):
        counts = dict(Job.objects.values_list("status").annotate(n=Count("id")))
        counts["total"] = sum(counts.values())
        extra = {"stats": counts, "companies": Company.objects.count()}
        return super().changelist_view(request, {**(extra_context or {}), **extra})


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "size", "headquarters", "website", "details_status")
    list_filter = ("details_status", "company_type")
    search_fields = ("name", "linkedin_id")
    readonly_fields = ("details_updated_at",)
    actions = ["retry_details"]

    @admin.action(description="Повторити збір даних (status=new)", permissions=["change"])
    def retry_details(self, request, queryset):
        n = queryset.update(details_status=Company.DetailsStatus.NEW,
                            details_attempts=0, details_error="")
        self.message_user(request, f"Повернено в чергу: {n}")




