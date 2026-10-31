from django.db import models


class SearchQuery(models.Model):
    keywords = models.CharField(max_length=255)
    country = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("keywords", "country")

    def __str__(self):
        return f"{self.keywords} / {self.country}"


class Company(models.Model):
    linkedin_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=500, blank=True)
    website = models.URLField(max_length=500, blank=True)
    industry = models.CharField(max_length=255, blank=True)
    size = models.CharField(max_length=100, blank=True)
    headquarters = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "companies"


class Job(models.Model):
    class Status(models.TextChoices):
        NEW = "new"
        PROCESSING = "processing"
        DONE = "done"
        FAILED = "failed"

    linkedin_job_id = models.CharField(max_length=64, unique=True)
    queries = models.ManyToManyField(SearchQuery, related_name="jobs")
    company = models.ForeignKey(Company, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="jobs")

    title = models.CharField(max_length=500)
    location = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=1000)
    posted_at = models.DateField(null=True, blank=True)

    # заповнюється на етапі Details
    description = models.TextField(blank=True)
    seniority = models.CharField(max_length=100, blank=True)
    employment_type = models.CharField(max_length=100, blank=True)
    job_function = models.CharField(max_length=255, blank=True)
    industries = models.CharField(max_length=255, blank=True)
    applicants = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.NEW, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


locked_at = models.DateTimeField(null=True, blank=True)

class Status(models.TextChoices):
    NEW = "new"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"