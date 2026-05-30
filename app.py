import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

from config import Config
from models import db, ScheduledPost
from services import process_ready_posts, ensure_upload_folder


ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "m4v", "webm"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    upload_folder = Path(app.config["UPLOAD_FOLDER"])
    ensure_upload_folder(upload_folder)

    with app.app_context():
        db.create_all()

    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html", app_timezone=app.config["APP_TIMEZONE"])

    @app.route("/submit", methods=["POST"])
    def submit():
        row_ids = request.form.getlist("row_ids")
        if not row_ids:
            flash("Add at least one video row.", "error")
            return redirect(url_for("index"))

        created_count = 0
        user_tz = ZoneInfo(app.config["APP_TIMEZONE"])

        for row_id in row_ids:
            video_file = request.files.get(f"video_file_{row_id}")
            if not video_file or not video_file.filename:
                continue

            if not is_allowed(video_file.filename, ALLOWED_VIDEO_EXTENSIONS):
                flash(f"Skipped {video_file.filename}: unsupported video type.", "error")
                continue

            title = request.form.get(f"title_{row_id}", "").strip()
            if not title:
                title = Path(video_file.filename).stem

            description = request.form.get(f"description_{row_id}", "").strip()
            tags = request.form.get(f"tags_{row_id}", "").strip()
            scheduled_local = request.form.get(f"scheduled_at_{row_id}", "").strip()
            channel_name = request.form.get(f"channel_name_{row_id}", "").strip()
            playlist = request.form.get(f"playlist_{row_id}", "").strip()
            platforms = request.form.getlist(f"platforms_{row_id}")

            if not platforms:
                flash(f"Skipped {video_file.filename}: choose at least one platform.", "error")
                continue

            try:
                if scheduled_local:
                    local_dt = datetime.fromisoformat(scheduled_local)
                    local_dt = local_dt.replace(tzinfo=user_tz)
                    scheduled_utc = local_dt.astimezone(timezone.utc)
                else:
                    scheduled_utc = datetime.now(timezone.utc)
            except ValueError:
                flash(f"Skipped {video_file.filename}: invalid scheduled date/time.", "error")
                continue

            video_path = save_upload(video_file, upload_folder)

            thumbnail_path = None
            thumbnail_file = request.files.get(f"thumbnail_file_{row_id}")
            if thumbnail_file and thumbnail_file.filename:
                if is_allowed(thumbnail_file.filename, ALLOWED_IMAGE_EXTENSIONS):
                    thumbnail_path = save_upload(thumbnail_file, upload_folder)
                else:
                    flash(f"Skipped thumbnail for {video_file.filename}: unsupported image type.", "error")

            for platform in platforms:
                job = ScheduledPost(
                    platform=platform,
                    title=title,
                    description=description,
                    tags=tags,
                    scheduled_at_utc=scheduled_utc,
                    channel_name=channel_name,
                    playlist=playlist,
                    video_path=video_path,
                    thumbnail_path=thumbnail_path,
                    status="queued",
                )
                db.session.add(job)
                created_count += 1

        db.session.commit()

        if created_count:
            flash(f"Created {created_count} scheduled upload job(s).", "success")
            return redirect(url_for("jobs"))

        flash("No jobs were created. Please check your rows and try again.", "error")
        return redirect(url_for("index"))

    @app.route("/jobs", methods=["GET"])
    def jobs():
        all_jobs = (
            ScheduledPost.query
            .order_by(ScheduledPost.created_at.desc())
            .limit(200)
            .all()
        )
        return render_template("jobs.html", jobs=all_jobs, app_timezone=app.config["APP_TIMEZONE"])

    @app.route("/admin/run-due", methods=["GET", "POST"])
    def run_due():
        key = request.args.get("key") or request.form.get("key")
        if key != app.config["ADMIN_RUN_KEY"]:
            return jsonify({"error": "Invalid or missing admin key."}), 403

        results = process_ready_posts(limit=10)
        return jsonify({"processed": len(results), "results": results})

    @app.route("/jobs/<int:job_id>/retry", methods=["POST"])
    def retry_job(job_id):
        job = ScheduledPost.query.get_or_404(job_id)
        job.status = "queued"
        job.error_message = None
        db.session.commit()
        flash(f"Job #{job.id} re-queued.", "success")
        return redirect(url_for("jobs"))

    @app.template_filter("localtime")
    def localtime(value):
        if not value:
            return ""
        tz = ZoneInfo(app.config["APP_TIMEZONE"])
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(tz).strftime("%Y-%m-%d %I:%M %p")

    return app


def save_upload(file_storage, upload_folder: Path):
    safe_name = secure_filename(file_storage.filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    path = upload_folder / unique_name
    file_storage.save(path)
    return str(path)


def is_allowed(filename, allowed_exts):
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in allowed_exts


app = create_app()


def start_scheduler_if_enabled(flask_app):
    if not flask_app.config["ENABLE_SCHEDULER"]:
        return

    scheduler = BackgroundScheduler(daemon=True)

    def tick():
        with flask_app.app_context():
            process_ready_posts(limit=5)

    scheduler.add_job(
        tick,
        "interval",
        seconds=flask_app.config["SCHEDULER_INTERVAL_SECONDS"],
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()


start_scheduler_if_enabled(app)


if __name__ == "__main__":
    app.run(debug=True)
