from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class ScheduledPost(db.Model):
    __tablename__ = "scheduled_posts"

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(32), nullable=False, index=True)

    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    tags = db.Column(db.String(1000), nullable=True)

    scheduled_at_utc = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    channel_name = db.Column(db.String(255), nullable=True)
    playlist = db.Column(db.String(255), nullable=True)

    video_path = db.Column(db.String(1000), nullable=False)
    thumbnail_path = db.Column(db.String(1000), nullable=True)

    status = db.Column(db.String(32), nullable=False, default="queued", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    external_id = db.Column(db.String(255), nullable=True)
    response_json = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def is_due(self):
        return self.scheduled_at_utc <= datetime.now(timezone.utc)
