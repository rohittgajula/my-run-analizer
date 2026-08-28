from django.contrib import admin

from .models import AIAnalysis, AIRequestLog


@admin.register(AIRequestLog)
class AIRequestLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "operation", "model", "status",
                    "input_tokens", "output_tokens", "estimated_cost_usd", "latency_ms")
    list_filter = ("operation", "status", "model")
    date_hierarchy = "created_at"


@admin.register(AIAnalysis)
class AIAnalysisAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "athlete", "model", "prompt_version")
    list_filter = ("kind", "model", "prompt_version")
