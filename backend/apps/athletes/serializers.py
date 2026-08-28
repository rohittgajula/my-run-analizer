from zoneinfo import ZoneInfo, available_timezones

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import Athlete, default_available_days

WEEKDAYS = {"0", "1", "2", "3", "4", "5", "6"}


class AthleteSerializer(serializers.ModelSerializer):
    training_days_per_week = serializers.IntegerField(read_only=True)
    zones = serializers.SerializerMethodField()

    def get_zones(self, athlete):
        """None when the data cannot support zones — the client shows nothing
        rather than a band derived from a population formula."""
        zones = athlete.zones()
        if zones is None:
            return None
        return {
            "resting_hr": zones.resting_hr,
            "max_hr": zones.max_hr,
            "max_source": zones.max_source,
            "zones": [
                {"name": z.name, "label": z.label, "low": z.low, "high": z.high,
                 "purpose": z.purpose}
                for z in zones.zones
            ],
        }

    class Meta:
        model = Athlete
        fields = [
            "id", "display_name", "timezone", "date_of_birth", "weight_kg",
            "resting_hr", "max_hr",
            "easy_pace_min", "easy_pace_max",
            "hr_easy_min", "hr_easy_max", "hr_ceiling",
            "run_cadence_threshold", "available_days", "long_run_day",
            "training_days_per_week", "onboarding_complete", "zones",
            "garmin_connected", "garmin_last_sync", "created_at", "updated_at",
        ]
        # System-managed. A client that could PATCH garmin_connected=True could make
        # the UI claim sync works when it does not.
        read_only_fields = [
            "id", "garmin_connected", "garmin_last_sync", "created_at", "updated_at",
            "zones",
        ]

    def validate_timezone(self, value):
        # A bad zone would not raise anywhere — local_now falls back to UTC — so every
        # date in the app would quietly shift. Reject it here instead.
        if value not in available_timezones():
            raise serializers.ValidationError(f"'{value}' is not a known timezone.")
        ZoneInfo(value)
        return value

    def validate_available_days(self, value):
        if not isinstance(value, dict) or set(value) != WEEKDAYS:
            raise serializers.ValidationError(
                'Must be an object with keys "0" (Monday) through "6" (Sunday).'
            )
        if not all(isinstance(v, bool) for v in value.values()):
            raise serializers.ValidationError("Every value must be true or false.")
        if not any(value.values()):
            # Zero training days makes the plan generator emit an empty plan with no
            # explanation. Far better to refuse the input than debug the output.
            raise serializers.ValidationError("Pick at least one day you can train.")
        return value

    def validate(self, attrs):
        def current(field):
            return attrs.get(field, getattr(self.instance, field, None))

        if current("easy_pace_min") >= current("easy_pace_max"):
            raise serializers.ValidationError(
                {"easy_pace_max": "The slow edge of the easy band must be slower than the fast edge."}
            )
        if not current("hr_easy_min") < current("hr_easy_max") < current("hr_ceiling"):
            raise serializers.ValidationError(
                {"hr_ceiling": "Heart-rate bands must increase: easy min < easy max < ceiling."}
            )

        days = current("available_days") or {}
        long_day = current("long_run_day")
        if days and not days.get(str(long_day), False):
            raise serializers.ValidationError(
                {"long_run_day": "Your long-run day must be a day you are available to train."}
            )
        return attrs


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    display_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=64, required=False, default="UTC")

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate_password(self, value):
        # Django's configured validators — length, commonness, numeric-only, similarity.
        validate_password(value)
        return value

    def validate_timezone(self, value):
        if value and value not in available_timezones():
            return "UTC"
        return value or "UTC"

    @transaction.atomic
    def create(self, validated):
        # Atomic on purpose: a User with no Athlete authenticates fine and then 500s
        # on every request that touches request.user.athlete.
        user = User.objects.create_user(
            username=validated["username"],
            email=validated.get("email", ""),
            password=validated["password"],
        )
        athlete = Athlete.objects.create(
            user=user,
            display_name=validated.get("display_name") or validated["username"],
            timezone=validated.get("timezone", "UTC"),
            available_days=default_available_days(),
        )
        return athlete


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]
        read_only_fields = fields
