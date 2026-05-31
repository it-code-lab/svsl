import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import text
from werkzeug.utils import secure_filename

from config import Config
from models import db, ScheduledPost
from services import process_ready_posts, ensure_upload_folder
from services.destination_cache import get_cached_option
from services.facebook_oauth import (
    build_facebook_authorization_url,
    exchange_facebook_code_for_token,
    get_facebook_token_status,
    list_facebook_pages,
    validate_facebook_state,
)
from services.pinterest_oauth import (
    build_pinterest_authorization_url,
    exchange_code_for_tokens,
    get_pinterest_token_status,
    list_pinterest_boards,
    refresh_pinterest_token,
    validate_pinterest_state,
)
from services.youtube_oauth import (
    get_youtube_token_status,
    list_youtube_channels,
    list_youtube_playlists,
)


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
        ensure_sqlite_schema_updates()

    @app.route("/", methods=["GET"])
    def index():
        youtube_status = get_youtube_token_status()
        pinterest_status = get_pinterest_token_status()
        facebook_status = get_facebook_token_status()

        youtube_channels, youtube_channels_error = _safe_destination_call(list_youtube_channels)
        pinterest_boards, pinterest_boards_error = _safe_destination_call(list_pinterest_boards)
        facebook_pages, facebook_pages_error = _safe_destination_call(list_facebook_pages)

        return render_template(
            "index.html",
            app_timezone=app.config["APP_TIMEZONE"],
            youtube_status=youtube_status,
            pinterest_status=pinterest_status,
            facebook_status=facebook_status,
            youtube_channels=youtube_channels,
            pinterest_boards=pinterest_boards,
            facebook_pages=facebook_pages,
            youtube_channels_error=youtube_channels_error,
            pinterest_boards_error=pinterest_boards_error,
            facebook_pages_error=facebook_pages_error,
        )

    @app.route("/cache/youtube/channels/refresh", methods=["POST"])
    def youtube_channels_refresh():
        try:
            channels = list_youtube_channels(force=True)
            flash(f"YouTube channels cache refreshed: {len(channels)} channel(s).", "success")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("index"))

    @app.route("/api/youtube/channels", methods=["GET"])
    def youtube_channels_api():
        try:
            channels = list_youtube_channels(force=request.args.get("force") == "true")
            return jsonify({"items": channels})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/youtube/channels/<channel_id>/playlists", methods=["GET"])
    def youtube_channel_playlists_api(channel_id):
        try:
            playlists = list_youtube_playlists(
                channel_id,
                force=request.args.get("force") == "true",
            )
            return jsonify({"items": playlists})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/oauth/pinterest/connect", methods=["GET"])
    def pinterest_connect():
        try:
            auth_url = build_pinterest_authorization_url()
            return redirect(auth_url)
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

    @app.route("/oauth/pinterest/callback", methods=["GET"])
    def pinterest_callback():
        error = request.args.get("error")
        if error:
            flash(f"Pinterest authorization failed: {error}", "error")
            return redirect(url_for("index"))

        code = request.args.get("code")
        state = request.args.get("state")

        if not code:
            flash("Pinterest authorization did not return a code.", "error")
            return redirect(url_for("index"))

        try:
            validate_pinterest_state(state)
            exchange_code_for_tokens(code)
            list_pinterest_boards(force=True)
            flash("Pinterest connected successfully and boards were cached.", "success")
        except Exception as exc:
            flash(str(exc), "error")

        return redirect(url_for("index"))

    @app.route("/oauth/pinterest/status", methods=["GET"])
    def pinterest_status():
        return jsonify(get_pinterest_token_status())

    @app.route("/oauth/pinterest/refresh", methods=["POST"])
    def pinterest_refresh():
        try:
            refresh_pinterest_token()
            list_pinterest_boards(force=True)
            flash("Pinterest token refreshed and boards cache updated.", "success")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("index"))

    @app.route("/cache/pinterest/boards/refresh", methods=["POST"])
    def pinterest_boards_refresh():
        try:
            boards = list_pinterest_boards(force=True)
            flash(f"Pinterest boards cache refreshed: {len(boards)} board(s).", "success")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("index"))

    @app.route("/api/pinterest/boards", methods=["GET"])
    def pinterest_boards_api():
        try:
            return jsonify({"items": list_pinterest_boards(force=request.args.get("force") == "true")})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/oauth/facebook/connect", methods=["GET"])
    def facebook_connect():
        try:
            auth_url = build_facebook_authorization_url()
            return redirect(auth_url)
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

    @app.route("/oauth/facebook/callback", methods=["GET"])
    def facebook_callback():
        error = request.args.get("error")
        if error:
            flash(f"Facebook authorization failed: {error}", "error")
            return redirect(url_for("index"))

        code = request.args.get("code")
        state = request.args.get("state")

        if not code:
            flash("Facebook authorization did not return a code.", "error")
            return redirect(url_for("index"))

        try:
            validate_facebook_state(state)
            exchange_facebook_code_for_token(code)
            pages = list_facebook_pages(force=True)
            flash(f"Facebook connected successfully and {len(pages)} Page(s) were cached.", "success")
        except Exception as exc:
            flash(str(exc), "error")

        return redirect(url_for("index"))

    @app.route("/oauth/facebook/status", methods=["GET"])
    def facebook_status():
        return jsonify(get_facebook_token_status())

    @app.route("/cache/facebook/pages/refresh", methods=["POST"])
    def facebook_pages_refresh():
        try:
            pages = list_facebook_pages(force=True)
            flash(f"Facebook Pages cache refreshed: {len(pages)} Page(s).", "success")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("index"))

    @app.route("/api/facebook/pages", methods=["GET"])
    def facebook_pages_api():
        try:
            pages = list_facebook_pages(force=request.args.get("force") == "true")
            # Do not expose cached Page access tokens through the API response.
            safe_pages = [
                {"id": page["id"], "name": page["name"], "updated_at_utc": page.get("updated_at_utc")}
                for page in pages
            ]
            return jsonify({"items": safe_pages})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/submit", methods=["POST"])
    def submit():
        row_ids = request.form.getlist("row_ids")
        if not row_ids:
            flash("Add at least one video row.", "error")
            return redirect(url_for("index"))

        platforms = request.form.getlist("platforms")
        if not platforms:
            flash("Choose at least one platform for this run.", "error")
            return redirect(url_for("index"))

        selected_destinations = {
            "youtube": request.form.get("youtube_channel_id", "").strip(),
            "facebook": request.form.get("facebook_page_id", "").strip(),
            "pinterest": request.form.get("pinterest_board_id", "").strip(),
        }
        youtube_playlist = request.form.get("youtube_playlist", "").strip()

        created_count = 0
        user_tz = ZoneInfo(app.config["APP_TIMEZONE"])

        for row_id in row_ids:
            video_file = request.files.get(f"video_file_{row_id}")

            title = request.form.get(f"title_{row_id}", "").strip()
            description = request.form.get(f"description_{row_id}", "").strip()
            tags = request.form.get(f"tags_{row_id}", "").strip()
            scheduled_local = request.form.get(f"scheduled_at_{row_id}", "").strip()
            pinterest_link_url = request.form.get(f"pinterest_link_url_{row_id}", "").strip()
            video_name = request.form.get(f"video_file_name_{row_id}", "").strip()
            thumbnail_name = request.form.get(f"thumbnail_file_name_{row_id}", "").strip()
            thumbnail_file = request.files.get(f"thumbnail_file_{row_id}")

            if not any(
                [
                    video_file and video_file.filename,
                    video_name,
                    thumbnail_file and thumbnail_file.filename,
                    thumbnail_name,
                    title,
                    description,
                    tags,
                    scheduled_local,
                    pinterest_link_url,
                ]
            ):
                continue

            try:
                if scheduled_local:
                    local_dt = datetime.fromisoformat(scheduled_local)
                    local_dt = local_dt.replace(tzinfo=user_tz)
                    scheduled_utc = local_dt.astimezone(timezone.utc)
                else:
                    scheduled_utc = datetime.now(timezone.utc)
            except ValueError:
                row_label = request.form.get(f"video_file_name_{row_id}", "").strip() or "a row"
                flash(f"Skipped {row_label}: invalid scheduled date/time.", "error")
                continue

            video_path = None
            if video_file and video_file.filename:
                if not is_allowed(video_file.filename, ALLOWED_VIDEO_EXTENSIONS):
                    flash(f"Skipped {video_file.filename}: unsupported video type.", "error")
                    continue
                video_path = save_upload(video_file, upload_folder)
            else:
                if video_name:
                    try:
                        video_path = resolve_library_file(
                            video_name,
                            app.config["VIDEO_LIBRARY_FOLDER"],
                            ALLOWED_VIDEO_EXTENSIONS,
                        )
                    except ValueError as exc:
                        flash(f"Skipped {video_name}: {exc}", "error")
                        continue

            if not video_path:
                flash("Skipped a row: choose a video file or provide a video filename.", "error")
                continue

            if not title:
                title = Path(video_path).stem

            thumbnail_path = None
            if thumbnail_file and thumbnail_file.filename:
                if is_allowed(thumbnail_file.filename, ALLOWED_IMAGE_EXTENSIONS):
                    thumbnail_path = save_upload(thumbnail_file, upload_folder)
                else:
                    flash(f"Skipped thumbnail for {Path(video_path).name}: unsupported image type.", "error")
            else:
                if thumbnail_name:
                    try:
                        thumbnail_path = resolve_library_file(
                            thumbnail_name,
                            app.config["THUMBNAIL_LIBRARY_FOLDER"],
                            ALLOWED_IMAGE_EXTENSIONS,
                        )
                    except ValueError as exc:
                        flash(f"Skipped thumbnail {thumbnail_name}: {exc}", "error")

            for platform in platforms:
                destination_id = selected_destinations.get(platform, "")
                destination_name = lookup_destination_name(platform, destination_id)

                job = ScheduledPost(
                    platform=platform,
                    title=title,
                    description=description,
                    tags=tags,
                    scheduled_at_utc=scheduled_utc,
                    channel_name=None,
                    playlist=youtube_playlist if platform == "youtube" else None,
                    destination_id=destination_id or None,
                    destination_name=destination_name,
                    video_path=video_path,
                    thumbnail_path=thumbnail_path,
                    link_url=pinterest_link_url if platform == "pinterest" else None,
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


def _safe_destination_call(fn):
    try:
        return fn(), None
    except Exception as exc:
        return [], str(exc)


def lookup_destination_name(platform: str, destination_id: str):
    if not destination_id:
        return None
    mapping = {
        "youtube": ("youtube", "channels"),
        "facebook": ("facebook", "pages"),
        "pinterest": ("pinterest", "boards"),
    }
    provider_option = mapping.get(platform)
    if not provider_option:
        return None
    cached = get_cached_option(provider_option[0], provider_option[1], destination_id)
    return cached["name"] if cached else None


def save_upload(file_storage, upload_folder: Path):
    safe_name = secure_filename(file_storage.filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    path = upload_folder / unique_name
    file_storage.save(path)
    return str(path)


def resolve_library_file(filename: str, folder: str, allowed_exts):
    if not filename:
        raise ValueError("missing filename")

    if not is_allowed(filename, allowed_exts):
        raise ValueError("unsupported file type")

    base_path = Path(folder).resolve()
    candidate = (base_path / filename).resolve()

    if candidate != base_path and base_path not in candidate.parents:
        raise ValueError("filename must stay inside the configured folder")

    if not candidate.exists() or not candidate.is_file():
        raise ValueError(f"file not found in {base_path}")

    return str(candidate)


def is_allowed(filename, allowed_exts):
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in allowed_exts


def ensure_sqlite_schema_updates():
    """Small local-dev schema updater for new nullable columns.

    db.create_all() creates new tables but does not alter existing SQLite tables.
    This helper keeps the starter convenient if you already ran an older version.
    For production, use Flask-Migrate/Alembic instead.
    """
    try:
        rows = db.session.execute(text("PRAGMA table_info(scheduled_posts)")).fetchall()
        existing = {row[1] for row in rows}
        additions = {
            "destination_id": "ALTER TABLE scheduled_posts ADD COLUMN destination_id VARCHAR(255)",
            "destination_name": "ALTER TABLE scheduled_posts ADD COLUMN destination_name VARCHAR(255)",
            "link_url": "ALTER TABLE scheduled_posts ADD COLUMN link_url VARCHAR(1000)",
        }
        for column, ddl in additions.items():
            if column not in existing:
                db.session.execute(text(ddl))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


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
    app.run(debug=True, port=5001)
