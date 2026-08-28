from rest_framework import serializers

from .models import JournalEntry


class JournalEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalEntry
        fields = [
            "id", "text", "reply", "source", "written_on", "applies_to_date",
            "pain_reported", "illness_reported", "rpe", "extracted",
            "extraction_failed", "created_at",
        ]
        read_only_fields = fields
