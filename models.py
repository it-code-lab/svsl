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

    # Platform-specific selected destination.
    # Examples: Pinterest board ID, Facebook Page ID.
    destination_id = db.Column(db.String(255), nullable=True, index=True)
    destination_name = db.Column(db.String(255), nullable=True)

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


class OAuthToken(db.Model):
    """Stores OAuth tokens for provider integrations.

    This starter app stores one Pinterest connection for the app/admin account.
    For a multi-user SaaS, add user_id/account_id and encrypt token fields.
    """

    __tablename__ = "oauth_tokens"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False, unique=True, index=True)

    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    token_type = db.Column(db.String(50), nullable=True)
    scope = db.Column(db.Text, nullable=True)

    expires_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    refresh_token_expires_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    raw_response_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CachedOption(db.Model):
    """Local cache for selectable destinations such as Pinterest boards and Facebook pages.

    This keeps API calls low for a local/personal installation.
    For a multi-user SaaS, add user_id/account_id and encrypt sensitive extra_json values.
    """

    __tablename__ = "cached_options"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False, index=True)
    option_type = db.Column(db.String(50), nullable=False, index=True)
    external_id = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    extra_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "provider",
            "option_type",
            "external_id",
            name="uq_cached_option_provider_type_external",
        ),
    )
