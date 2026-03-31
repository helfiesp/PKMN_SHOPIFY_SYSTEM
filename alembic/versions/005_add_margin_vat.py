"""Add margin_vat_products and margin_vat_proof_images tables.

Revision ID: 005
Revises: 004
Create Date: 2026-03-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005_add_margin_vat'
down_revision = '004_add_purchase_orders'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'margin_vat_products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_shopify_id', sa.String(length=255), nullable=False),
        sa.Column('variant_shopify_id', sa.String(length=255), nullable=False),
        sa.Column('product_title', sa.String(length=500), nullable=True),
        sa.Column('variant_title', sa.String(length=500), nullable=True),
        sa.Column('sku', sa.String(length=255), nullable=True),
        sa.Column('image_url', sa.String(length=1000), nullable=True),
        sa.Column('purchase_price_nok', sa.Float(), nullable=False),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('seller_description', sa.String(length=500), nullable=True),
        sa.Column('selling_price_nok', sa.Float(), nullable=True),
        sa.Column('margin_nok', sa.Float(), nullable=True),
        sa.Column('vat_amount_nok', sa.Float(), nullable=True),
        sa.Column('effective_rate_pct', sa.Float(), nullable=True),
        sa.Column('bucket_rate_pct', sa.Integer(), nullable=True),
        sa.Column('tax_collection_id', sa.String(length=255), nullable=True),
        sa.Column('tax_collection_name', sa.String(length=100), nullable=True),
        sa.Column('needs_reassignment', sa.Boolean(), default=False),
        sa.Column('status', sa.String(length=50), default='active'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('variant_shopify_id'),
    )
    op.create_index('ix_margin_vat_products_id', 'margin_vat_products', ['id'])
    op.create_index('ix_margin_vat_products_product_shopify_id', 'margin_vat_products', ['product_shopify_id'])
    op.create_index('ix_margin_vat_products_variant_shopify_id', 'margin_vat_products', ['variant_shopify_id'])
    op.create_index('idx_mvp_bucket_status', 'margin_vat_products', ['bucket_rate_pct', 'status'])

    op.create_table(
        'margin_vat_proof_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('margin_vat_product_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('stored_filename', sa.String(length=500), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['margin_vat_product_id'], ['margin_vat_products.id']),
    )
    op.create_index('ix_margin_vat_proof_images_id', 'margin_vat_proof_images', ['id'])


def downgrade() -> None:
    op.drop_table('margin_vat_proof_images')
    op.drop_table('margin_vat_products')
