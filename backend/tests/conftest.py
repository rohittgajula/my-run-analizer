import pytest
from django.contrib.auth.models import User

from apps.athletes.models import Athlete


@pytest.fixture
def athlete(db):
    user = User.objects.create_user("tester", password="correct-horse-battery-1")
    return Athlete.objects.create(
        user=user, display_name="Tester", timezone="Asia/Kolkata"
    )
