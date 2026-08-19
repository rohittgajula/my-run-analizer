import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_reports_both_dependencies(client):
    response = client.get(reverse("health"))
    body = response.json()

    assert response.status_code == 200, body
    assert body == {"status": "ok", "db": True, "redis": True}
