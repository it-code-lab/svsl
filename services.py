import json
from datetime import datetime, timezone, timedelta

from models import db, ScheduledPost
from providers import get_provider


def provider_ready_to_upload(job, provider, now):
    """Return True when this job should be sent to the platform now.

    Native-schedule platforms are sent early so the platform can hold the post
    and publish later. Non-native platforms are held locally until due time.
    """
    if provider.supports_native_schedule:
        max_seconds = provider.native_schedule_max_seconds
        if max_seconds is not None and job.scheduled_at_utc > now + timedelta(seconds=max_seconds):
            return False
        return True

    return job.scheduled_at_utc <= now


def process_ready_posts(limit=5, scan_limit=100):
    now = datetime.now(timezone.utc)

    candidates = (
        ScheduledPost.query
        .filter(ScheduledPost.status.in_(["queued", "retry"]))
        .order_by(ScheduledPost.scheduled_at_utc.asc())
        .limit(scan_limit)
        .all()
    )

    results = []

    for job in candidates:
        if len(results) >= limit:
            break

        provider = get_provider(job.platform)

        if not provider_ready_to_upload(job, provider, now):
            continue

        was_future_scheduled = job.scheduled_at_utc > now

        job.status = "running"
        job.attempts += 1
        job.error_message = None
        db.session.commit()

        result = provider.upload(job)

        if result.success:
            if provider.supports_native_schedule and was_future_scheduled:
                job.status = "remote_scheduled"
            else:
                job.status = "uploaded"

            job.external_id = result.external_id
            job.response_json = json.dumps(result.response or {}, ensure_ascii=False)
            job.error_message = None
        else:
            job.status = "retry" if job.attempts < 3 else "failed"
            job.response_json = json.dumps(result.response or {}, ensure_ascii=False)
            job.error_message = result.error or "Unknown error"

        db.session.commit()

        results.append(
            {
                "job_id": job.id,
                "platform": job.platform,
                "status": job.status,
                "external_id": job.external_id,
                "error": job.error_message,
            }
        )

    return results


# Backward-compatible name used by older routes/imports.
def process_due_posts(limit=5):
    return process_ready_posts(limit=limit)


def ensure_upload_folder(path):
    path.mkdir(parents=True, exist_ok=True)
