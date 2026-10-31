from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from .models import Company, Job, SearchQuery


class BulkForm(forms.Form):
    keywords = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 8, "cols": 60}),
        help_text="Одна фраза на рядок: Python Developer, Django Developer...",
    )
    locations = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 12, "cols": 60}),
        help_text="Одна локація на рядок: United States, Austin, Texas, United States...",
    )


def lines(text):
    return list(dict.fromkeys(l.strip() for l in text.splitlines() if l.strip()))


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    change_list_template = "admin/jobs/searchquery/change_list.html"
    list_display = ("keywords", "country", "is_active", "last_run_at", "total", "done")
    list_filter = ("is_active", "country")
    search_fields = ("keywords", "country")
    actions = ["run_again", "deactivate"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _total=Count("jobs", distinct=True),
            _done=Count("jobs", filter=Q(jobs__status="done"), distinct=True),
        )

    @admin.display(description="Вакансій", ordering="_total")
    def total(self, obj):
        return obj._total

    @admin.display(description="Оброблено", ordering="_done")
    def done(self, obj):
        return obj._done

    @admin.action(description="Запустити пошук ще раз", permissions=["change"])
    def run_again(self, request, queryset):
        n = queryset.update(last_run_at=None, locked_at=None)
        self.message_user(request, f"Поставлено в чергу: {n}")

    @admin.action(description="Вимкнути", permissions=["change"])
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)

    def get_urls(self):
        return [
            path("bulk-add/", self.admin_site.admin_view(self.bulk_add),
                 name="jobs_searchquery_bulk_add"),
        ] + super().get_urls()

    def bulk_add(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        if request.method == "POST":
            form = BulkForm(request.POST)
            if form.is_valid():
                kws = lines(form.cleaned_data["keywords"])
                locs = lines(form.cleaned_data["locations"])
                existing = set(SearchQuery.objects.values_list("keywords", "country"))
                new = [SearchQuery(keywords=k, country=l)
                       for k in kws for l in locs if (k, l) not in existing]
                SearchQuery.objects.bulk_create(new)
                self.message_user(
                    request,
                    f"Створено {len(new)} запитів, пропущено дублів: {len(kws) * len(locs) - len(new)}",
                    messages.SUCCESS,
                )
                return redirect("admin:jobs_searchquery_changelist")
        else:
            form = BulkForm()
        ctx = {**self.admin_site.each_context(request), "form": form,
               "title": "Масове додавання запитів", "opts": self.model._meta}
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
    list_display = ("name", "industry", "size", "headquarters")
    search_fields = ("name",)