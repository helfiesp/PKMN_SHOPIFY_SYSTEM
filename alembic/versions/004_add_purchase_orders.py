"""Add purchase_orders and purchase_order_items tables.

Revision ID: 004
Revises: 003
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_add_purchase_orders'
down_revision = '003_add_sales_velocity'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add weight_grams to existing variants table
    with op.batch_alter_table('variants') as batch_op:
        batch_op.add_column(sa.Column('weight_grams', sa.Float(), nullable=True))

    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('shipping_cost_jpy', sa.Float(), default=0.0),
        sa.Column('total_nok', sa.Float(), nullable=False),
        sa.Column('fx_rate_snapshot', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=50), default='completed'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_po_status_date', 'purchase_orders', ['status', 'order_date'])

    op.create_table(
        'purchase_order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_order_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('price_jpy', sa.Float(), nullable=False),
        sa.Column('weight_grams', sa.Float(), nullable=True),
        sa.Column('product_title', sa.String(length=500), nullable=True),
        sa.Column('variant_title', sa.String(length=500), nullable=True),
        sa.Column('sku', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id']),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id']),
    )
    op.create_index('idx_poi_order_variant', 'purchase_order_items',
                     ['purchase_order_id', 'variant_id'])


def downgrade() -> None:
    op.drop_index('idx_poi_order_variant', table_name='purchase_order_items')
    op.drop_table('purchase_order_items')
    op.drop_index('idx_po_status_date', table_name='purchase_orders')
    op.drop_table('purchase_orders')
    with op.batch_alter_table('variants') as batch_op:
        batch_op.drop_column('weight_grams')
