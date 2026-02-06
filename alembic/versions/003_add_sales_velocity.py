"""Add competitor_sales_velocity table for tracking sales metrics.

Revision ID: 003
Revises: 002
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_add_sales_velocity'
down_revision = '002_add_scan_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create competitor_sales_velocity table
    op.create_table(
        'competitor_sales_velocity',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('competitor_product_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.String(length=10), nullable=False),
        sa.Column('period_end', sa.String(length=10), nullable=False),
        sa.Column('period_days', sa.Integer(), nullable=False),
        sa.Column('starting_stock', sa.Integer(), default=0),
        sa.Column('ending_stock', sa.Integer(), default=0),
        sa.Column('min_stock', sa.Integer(), default=0),
        sa.Column('max_stock', sa.Integer(), default=0),
        sa.Column('total_units_sold', sa.Integer(), default=0),
        sa.Column('total_units_restocked', sa.Integer(), default=0),
        sa.Column('avg_daily_sales', sa.Float(), default=0.0),
        sa.Column('days_in_stock', sa.Integer(), default=0),
        sa.Column('days_out_of_stock', sa.Integer(), default=0),
        sa.Column('sellout_speed_days', sa.Float(), nullable=True),
        sa.Column('times_restocked', sa.Integer(), default=0),
        sa.Column('times_sold_out', sa.Integer(), default=0),
        sa.Column('avg_price', sa.Float(), nullable=True),
        sa.Column('price_at_fastest_sales', sa.Float(), nullable=True),
        sa.Column('last_calculated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['competitor_product_id'], ['competitor_products.id'])
    )
    
    # Create indexes
    op.create_index('idx_sales_velocity_product_period', 'competitor_sales_velocity', 
                    ['competitor_product_id', 'period_start', 'period_end'], unique=True)
    op.create_index('idx_sales_velocity_competitor_product', 'competitor_sales_velocity', 
                    ['competitor_product_id'])
    op.create_index('idx_sales_velocity_period_start', 'competitor_sales_velocity', 
                    ['period_start'])
    op.create_index('idx_sales_velocity_period_end', 'competitor_sales_velocity', 
                    ['period_end'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_sales_velocity_period_end', table_name='competitor_sales_velocity')
    op.drop_index('idx_sales_velocity_period_start', table_name='competitor_sales_velocity')
    op.drop_index('idx_sales_velocity_competitor_product', table_name='competitor_sales_velocity')
    op.drop_index('idx_sales_velocity_product_period', table_name='competitor_sales_velocity')
    
    # Drop table
    op.drop_table('competitor_sales_velocity')
