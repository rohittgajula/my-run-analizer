"""Re-parse stored .fit files without re-downloading them.

This is the payoff for keeping raw bytes permanently. Two situations need it:

* A parser or ingestion bug wrote nothing, or wrote it wrongly. Re-run and the
  history is rebuilt from source.
* The segmentation algorithm changes (M2 onward). Every past activity then needs
  reprocessing, and re-fetching from Garmin is both slow and rate-limited.
"""

from django.core.management.base import BaseCommand

from apps.activities.models import Activity
from apps.ingest.models import RawFitFile
from apps.ingest.services import DuplicateActivity, ingest_fit


class Command(BaseCommand):
    help = "Re-parse stored raw .fit files into activities."

    def add_arguments(self, parser):
        parser.add_argument("--athlete", type=int, help="Limit to one athlete id.")
        parser.add_argument(
            "--status", default="failed",
            help="Which raw files to process: failed (default), pending, parsed, all.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Delete any existing Activity for the file first, then re-parse.",
        )

    def handle(self, *args, **options):
        files = RawFitFile.objects.all()
        if options["athlete"]:
            files = files.filter(athlete_id=options["athlete"])
        if options["status"] != "all":
            files = files.filter(status=options["status"])

        imported = skipped = failed = 0

        for raw in files.order_by("uploaded_at"):
            # The Garmin activity id is not on RawFitFile, so recover it from the
            # filename the download produced: "<activityId>_ACTIVITY.fit".
            stem = raw.original_name.split("_")[0]
            garmin_id = int(stem) if stem.isdigit() else None

            if options["force"] and garmin_id is not None:
                Activity.objects.filter(
                    athlete=raw.athlete, garmin_activity_id=garmin_id
                ).delete()

            try:
                activity = ingest_fit(raw, garmin_activity_id=garmin_id)
            except DuplicateActivity:
                skipped += 1
                continue
            except Exception as exc:  # noqa: BLE001 — one bad file must not stop the run
                failed += 1
                self.stderr.write(self.style.ERROR(f"{raw.original_name}: {exc}"))
                continue

            imported += 1
            self.stdout.write(
                f"{activity.local_date}  {activity.total_distance_m / 1000:6.2f} km  "
                f"{activity.records.count():5d} records  {raw.original_name}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{imported} imported, {skipped} already stored, {failed} failed"
            )
        )
