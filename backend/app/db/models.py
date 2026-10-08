"""Database tables. See the Data model section of CLAUDE.md.

stores, products, variants, and events are global: each product is stored once,
no matter how many users watch it. User-owned tables are added with their slices.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC in Python.

    SQLite has no timezone support and hands back naive datetimes, so this
    converts to UTC on the way in and re-attaches UTC on the way out.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("naive datetime; use a timezone-aware UTC datetime")
            value = value.astimezone(UTC)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    # Named constraints, so later migrations can find and drop them (SQLite needs this).
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            # column_0_N_name joins every column, so two constraints starting with the same
            # column still get different names.
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Stores the enum's values as plain strings (works on any DB).

    Invalid values are rejected in Python before they reach the DB.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class Platform(StrEnum):
    SHOPIFY = "shopify"
    SHOPIFY_HYDROGEN = "shopify_hydrogen"


class StoreStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class EventType(StrEnum):
    RESTOCK = "restock"
    SOLD_OUT = "sold_out"
    PRICE_DROP = "price_drop"
    NEW_PRODUCT = "new_product"


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    domain: Mapped[str] = mapped_column(String(255), unique=True)
    platform: Mapped[Platform] = mapped_column(str_enum(Platform), default=Platform.SHOPIFY)
    enabled: Mapped[bool] = mapped_column(default=True)
    hot_interval_s: Mapped[int]
    sweep_interval_s: Mapped[int]
    status: Mapped[StoreStatus] = mapped_column(str_enum(StoreStatus), default=StoreStatus.OK)
    last_ok_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    consecutive_errors: Mapped[int] = mapped_column(default=0)

    products: Mapped[list["Product"]] = relationship(back_populates="store", lazy="raise")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("store_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    # Shopify's own id. Stored as text: Shopify ids are larger than a 32-bit int.
    external_id: Mapped[str] = mapped_column(String(32))
    handle: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    vendor: Mapped[str | None] = mapped_column(String(255))
    image_url: Mapped[str | None] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(1000))
    # Normalized title, handle, tags, body, and SKUs, used by style-code/keyword matching.
    search_text: Mapped[str] = mapped_column(Text, default="")
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    store: Mapped[Store] = relationship(back_populates="products", lazy="raise")
    variants: Mapped[list["Variant"]] = relationship(
        back_populates="product", lazy="raise", order_by="Variant.position, Variant.id"
    )


class Variant(Base):
    """One size of a product."""

    __tablename__ = "variants"
    __table_args__ = (UniqueConstraint("product_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    external_id: Mapped[str] = mapped_column(String(32))
    size: Mapped[str] = mapped_column(String(100))
    sku: Mapped[str | None] = mapped_column(String(100))
    price_cents: Mapped[int]
    available: Mapped[bool]
    # Where this size sits in the store's own order (0 = first). A size the store adds
    # later gets a higher id, so ids can't be used for ordering.
    position: Mapped[int] = mapped_column(default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    product: Mapped[Product] = relationship(back_populates="variants", lazy="raise")


class Event(Base):
    """Something that changed: the engine's output, read by everything downstream."""

    __tablename__ = "events"
    # For a product's event timeline, newest first.
    __table_args__ = (Index("ix_events_product_id_occurred_at", "product_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    # Null for product-level events such as new_product.
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("variants.id"))
    type: Mapped[EventType] = mapped_column(str_enum(EventType))
    old_value: Mapped[str | None] = mapped_column(String(100))
    new_value: Mapped[str | None] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Always stored lowercase, so "A@x.com" and "a@x.com" can't both register.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    # An argon2 hash, never the password itself.
    password_hash: Mapped[str] = mapped_column(String(255))
    # Admins can enable or disable stores, which are shared by every user.
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", lazy="raise", passive_deletes=True
    )


class UserSession(Base):
    """One logged-in browser. Named UserSession so it isn't confused with a DB session."""

    __tablename__ = "sessions"

    # The random token the browser sends back in its cookie.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Deleting a user logs them out everywhere.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(back_populates="sessions", lazy="raise")
