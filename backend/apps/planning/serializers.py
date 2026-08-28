from rest_framework import serializers

from .models import Race


class RaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Race
        fields = ["id", "name", "date", "distance_km", "is_target", "notes"]

    def validate(self, attrs):
        athlete = self.context["request"].user.athlete
        target = attrs.get("is_target", getattr(self.instance, "is_target", False))
        if target:
            # Two A races means two ramps, and the resolver would silently pick the
            # earlier one. Refuse rather than let the plan disagree with itself.
            existing = Race.objects.filter(athlete=athlete, is_target=True)
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    {"is_target": "You already have a target race. Unset that one first."}
                )
        return attrs
