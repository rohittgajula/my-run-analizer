"""Run the coaching evals.

    python manage.py evals            # against recorded responses, free
    python manage.py evals --live     # re-records against the API, costs money

Run --live after any prompt change, then commit the recordings so the next run is
free and the diff shows what actually changed.
"""

from django.core.management.base import BaseCommand

from apps.coaching.evals.fixtures import FIXTURES
from apps.coaching.evals.runner import run_all


class Command(BaseCommand):
    help = "Evaluate the coaching prompts against fixture athletes."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true",
                            help="Call the API and re-record. Costs money.")
        parser.add_argument("--only", help="Run a single fixture by name.")

    def handle(self, *args, **options):
        why = {f.name: f.why for f in FIXTURES}
        results = run_all(live=options["live"], only=options["only"])

        if not results:
            self.stderr.write(self.style.ERROR("No fixtures matched."))
            return

        for result in results:
            mark = self.style.SUCCESS("PASS") if result.ok else self.style.ERROR("FAIL")
            source = "recorded" if result.cached else "live"
            self.stdout.write(f"{mark}  {result.fixture} ({source})")
            self.stdout.write(f"        {why[result.fixture]}")
            for failure in result.failures:
                self.stdout.write(self.style.WARNING(f"        · {failure}"))

        failed = [r for r in results if not r.ok]
        self.stdout.write("")
        if failed:
            self.stdout.write(self.style.ERROR(
                f"{len(failed)} of {len(results)} fixtures failed."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f"All {len(results)} fixtures passed."))
