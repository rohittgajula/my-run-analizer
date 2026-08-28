from django.contrib import admin

from .models import JournalEntry


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("applies_to_date", "athlete", "pain_reported", "illness_reported",
                    "rpe", "extraction_failed")
    list_filter = ("pain_reported", "illness_reported", "extraction_failed", "source")
    date_hierarchy = "applies_to_date"
