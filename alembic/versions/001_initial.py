"""Initial migration - create all tables.

Revision ID: 001_initial
Revises: 
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Products table
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shopify_id', sa.String(255), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('handle', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50)),
        sa.Column('template_suffix', sa.String(100)),
        sa.Column('collection_id', sa.String(255)),
        sa.Column('is_preorder', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('last_synced_at', sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_products_shopify_id', 'products', ['shopify_id'], unique=True)
    op.create_index('ix_products_handle', 'products', ['handle'])
    op.create_index('ix_products_collection_id', 'products', ['collection_id'])
    
    # Add more table creation statements...
    # (Full migration would include all tables from models.py)


def downgrade():
    op.drop_table('products')
    # Drop other tables...
