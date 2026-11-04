from django import forms
from django.contrib import admin, messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Min
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from .locations import US_LOCATIONS
from .models import Company, Job, SearchQuery

CACHE_KEY = "sq_stats_v3"


class BulkForm(forms.Form):
    keywords = forms.CharField(
        label="Ключові слова",
        widget=forms.Textarea(attrs={"rows": 10, "cols": 60}),
        help_text="Одне ключове слово на рядок. Для кожного автоматично "
                  "створюються запити по всіх штатах і великих містах США.",
    )


def lines(text):
    return list(dict.fromkeys(l.strip() for l in text.splitlines() if l.strip()))


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    change_list_template = "admin/jobs/searchquery/change_list.html"
    list_display = ("keywords", "vacancies")
    search_fields = ("keywords",)
    ordering = ("keywords", "id")
    list_per_page = 50
    actions = ["run_again", "deactivate", "activate"]

    def has_add_permission(self, request):
        # стандартну кнопку Add прибрано, додавання лише через "Додати ключове слово"
        return False

    def changelist_view(self, request, extra_context=None):
        can_bulk = request.user.has_perm("jobs.add_searchquery")
        return super().changelist_view(
            request, {**(extra_context or {}), "can_bulk": can_bulk})

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        match = getattr(request, "resolver_match", None)
        # у списку один рядок на ключове слово
        if match and match.url_name == "jobs_searchquery_changelist":
            first_ids = (SearchQuery.objects.values("keywords")
                         .annotate(m=Min("id")).values("m"))
            qs = qs.filter(id__in=first_ids)
        return qs

    def _get_vacancies(self):
        data = cache.get(CACHE_KEY)
        if data is None:
            data = dict(
                Job.objects.values_list("queries__keywords")
                .annotate(n=Count("id", distinct=True))
            )
            cache.set(CACHE_KEY, data, 60)
        return data

    @admin.display(description="Вакансій")
    def vacancies(self, obj):
        return self._get_vacancies().get(obj.keywords, 0)

    # дії діють на ВСІ запити вибраного ключового слова
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

    def bulk_add(self, request):
        if not request.user.has_perm("jobs.add_searchquery"):
            raise PermissionDenied
        if request.method == "POST":
            form = BulkForm(request.POST)
            if form.is_valid():
                kws = lines(form.cleaned_data["keywords"])
                existing = set(
                    SearchQuery.objects.filter(filters="")
                    .values_list("keywords", "country")
                )
                new = [SearchQuery(keywords=k, country=loc, filters="")
                       for k in kws for loc in US_LOCATIONS
                       if (k, loc) not in existing]
                SearchQuery.objects.bulk_create(new, ignore_conflicts=True)
                cache.delete(CACHE_KEY)
                self.message_user(
                    request,
                    f"Ключових слів: {len(kws)}, створено запитів: {len(new)}",
                    messages.SUCCESS,
                )
                return redirect("admin:jobs_searchquery_changelist")
        else:
            form = BulkForm()
        ctx = {**self.admin_site.each_context(request), "form": form,
               "title": "Додати ключове слово", "opts": self.model._meta}
        return TemplateResponse(request, "admin/jobs/bulk_add.html", ctx)


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