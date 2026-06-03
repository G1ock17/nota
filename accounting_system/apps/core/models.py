from django.db import models
from django.utils.text import slugify


class TimeStampedModel(models.Model):
    """Abstract base adding created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(models.Model):
    """Top-level tenant. All business data is scoped to an organization."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    # NOTE: no `choices` here on purpose — it must match the existing migration.
    currency = models.CharField(default="RUB", max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "org"
            slug = base
            i = 2
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


class OrganizationOwned(models.Model):
    """Abstract base for every tenant-scoped model."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="%(class)s_set",
    )

    class Meta:
        abstract = True
