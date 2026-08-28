"""Segment activities and compute their metrics.

By default only touches activities whose stored `segmentation_version` predates the
current ALGORITHM_VERSION — which is the whole reason that field is an integer rather
than a boolean. Bump the version, run this, and history is rebuilt.
"""

from django.core.management.base import BaseCommand

from analysis.segmentation import ALGORITHM_VERSION

from apps.activities.models import Activity
from apps.activities.services import derive


class Command(BaseCommand):
    help = "Derive segments and metrics for activities."

    def add_arguments(self, parser):
        parser.add_argument("--athlete", type=int)
        parser.add_argument("--all", action="store_true",
                            help="Re-derive everything, not just stale rows.")

    def handle(self, *args, **options):
        activities = Activity.objects.all()
        if options["athlete"]:
            activities = activities.filter(athlete_id=options["athlete"])
        if not options["all"]:
            # Only rows not yet seen by this algorithm version. Bump
            # ALGORITHM_VERSION and re-run to rebuild history.
            activities = activities.exclude(segmentation_version=ALGORITHM_VERSION)

        derived = skipped = 0
        for activity in activities.order_by("local_date"):
            metrics = derive(activity)
            if metrics is None:
                skipped += 1
                self.stdout.write(
                    f"  {activity.local_date}  {activity.sport:<10} not segmentable"
                )
                continue

            derived += 1
            self.stdout.write(
                f"  {activity.local_date}  {activity.sport:<10} "
                f"{metrics.run_distance_m:6.0f} m run / "
                f"{metrics.walk_distance_m:6.0f} m walk  "
                f"({metrics.run_fraction:.0%})  "
                f"{metrics.run_block_count} blocks  "
                f"longest {metrics.longest_run_s / 60:.1f} min"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\n{derived} derived, {skipped} not segmentable (algorithm v{ALGORITHM_VERSION})"
        ))
