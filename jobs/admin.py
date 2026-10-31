from django.contrib import admin
from .models import SearchQuery, Job, Company


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ("keywords", "country", "is_active", "last_run_at")
    list_filter = ("is_active", "country")
    search_fields = ("keywords",)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "location", "status", "attempts", "posted_at")
    list_filter = ("status", "queries__country", "employment_type", "seniority")
    search_fields = ("title", "company__name", "linkedin_job_id")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("company",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "size", "headquarters")
    search_fields = ("name",)