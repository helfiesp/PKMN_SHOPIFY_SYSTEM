from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    Date,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

TZ = ZoneInfo("Europe/Oslo")


def now_utc() -> datetime:
    return datetime.utcnow()


def today_oslo() -> date:
    return datetime.now(TZ).date()


# ---------------------------
# Your own store products
# ---------------------------
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    website = Column(String, index=True)
    name = Column(String, nullable=False)
    price = Column(String)  # øre as string, keep legacy
    product_link = Column(String)
    created_at = Column(DateTime, default=now_utc, nullable=False)


# ---------------------------
# Scraper status (health)
# ---------------------------
class ScraperStatus(Base):
    __tablename__ = "scraper_status"

    id = Column(Integer, primary_key=True, index=True)
    scraper_name = Column(String, unique=True, index=True, nullable=False)
    last_attempt = Column(DateTime)
    last_success = Column(DateTime)
    last_error = Column(Text)



class CatalogProduct(Base):
    """
    Your "master" product. This is what you link competitor offers to.
    Holds SKU and your canonical fields.
    """
    __tablename__ = "catalog_products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True, nullable=True)  # optional but recommended
    name = Column(String, nullable=False)
    normalized_name = Column(String, index=True, nullable=True)
    category = Column(String, index=True, nullable=True)
    brand = Column(String, index=True, nullable=True)
    language = Column(String, index=True, nullable=True)

    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, nullable=False)



class CompetitorProductFix(Base):
    """
    Persistent, per-row manual fixes for scraped competitor products.
    Any non-null field overrides the scraped value in the API.
    """
    __tablename__ = "competitor_product_fixes"

    id = Column(Integer, primary_key=True, index=True)
    competitor_product_id = Column(
        Integer,
        ForeignKey("competitor_products.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Override fields (nullable => "don't override")
    website = Column(String, nullable=True)
    product_link = Column(String, nullable=True)

    name = Column(String, nullable=True)
    normalized_name = Column(String, nullable=True)
    category = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    language = Column(String, nullable=True)

    price = Column(String, nullable=True)          # øre string
    stock_status = Column(String, nullable=True)
    stock_amount = Column(Integer, nullable=True)

    updated_at = Column(DateTime, default=now_utc, nullable=False)

    __table_args__ = (
        Index("ix_fix_competitor_product_id", "competitor_product_id"),
    )

# ---------------------------
# Competitor products (latest state)
# ---------------------------
class CompetitorProduct(Base):
    __tablename__ = "competitor_products"

    id = Column(Integer, primary_key=True, index=True)

    website = Column(String, index=True, nullable=False)         # e.g. cardcenter, boosterpakker
    product_link = Column(String, index=True, nullable=False)    # stable key (scheme://host/path)

    name = Column(String, nullable=False)
    normalized_name = Column(String, index=True)  # canonicalized normalized identity
    category = Column(String, index=True)
    brand = Column(String, index=True)
    language = Column(String, index=True, default="en")

    price = Column(String)            # øre as string for now
    stock_status = Column(String)     # "På lager" / "Utsolgt"
    stock_amount = Column(Integer)    # nullable for "unknown"

    created_at = Column(DateTime, default=now_utc, nullable=False)
    last_updated = Column(DateTime, default=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("website", "product_link", name="uq_competitor_site_link"),
        Index("ix_competitor_norm_cat", "normalized_name", "category"),
        Index("ix_competitor_norm_lang", "normalized_name", "language"),
    )


# ---------------------------
# One row per product per Oslo day
# ---------------------------
class CompetitorProductDaily(Base):
    __tablename__ = "competitor_products_daily"

    id = Column(Integer, primary_key=True, index=True)

    competitor_product_id = Column(Integer, index=True, nullable=False)
    website = Column(String, index=True, nullable=False)
    product_link = Column(String, index=True, nullable=False)

    day = Column(Date, index=True, nullable=False)  # Oslo day boundary
    price = Column(String)
    stock_status = Column(String)
    stock_amount = Column(Integer)

    scraped_at = Column(DateTime, default=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("competitor_product_id", "day", name="uq_competitor_daily_product_day"),
    )


# ---------------------------
# Snapshot per run (high-res movement)
# ---------------------------
class CompetitorProductSnapshot(Base):
    __tablename__ = "competitor_products_snapshot"

    id = Column(Integer, primary_key=True, index=True)

    competitor_product_id = Column(Integer, index=True, nullable=False)
    website = Column(String, index=True, nullable=False)
    product_link = Column(String, index=True, nullable=False)

    price = Column(String)
    stock_status = Column(String)
    stock_amount = Column(Integer)

    created_at = Column(DateTime, default=now_utc, nullable=False)


# ---------------------------
# Manual overrides for normalization/classification
# ---------------------------
class CompetitorProductOverride(Base):
    """
    Manual edits that survive future scrapes.

    Scope:
      - website=None => global override for all websites for that (normalized_name, category)
      - website="cardcenter" => only that website

    Any non-null override field wins.
    """
    __tablename__ = "competitor_product_overrides"

    id = Column(Integer, primary_key=True, index=True)

    # matching key
    normalized_name = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=True)
    website = Column(String, index=True, nullable=True)

    # override values (nullable = "don't override")
    brand = Column(String, nullable=True)
    language = Column(String, nullable=True)

    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, nullable=False)

    __table_args__ = (
        Index("ix_override_lookup", "website", "normalized_name", "category"),
    )


class CompetitorProductLink(Base):
    """
    Links ONE competitor product row to ONE catalog product.
    (A catalog product can have MANY competitor products linked.)
    """
    __tablename__ = "competitor_product_links"

    id = Column(Integer, primary_key=True, index=True)

    competitor_product_id = Column(
        Integer,
        ForeignKey("competitor_products.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    catalog_product_id = Column(
        Integer,
        ForeignKey("catalog_products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    created_at = Column(DateTime, default=now_utc, nullable=False)

    __table_args__ = (
        Index("ix_link_catalog_product_id", "catalog_product_id"),
    )
    