"""Add scan_logs table for tracking competitor scraper runs.

Revision ID: 002
Revises: 001
Create Date: 2026-01-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_scan_logs'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create scan_logs table
    op.create_table(
        'scan_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scraper_name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('output', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index on scraper_name and created_at
    op.create_index('idx_scan_log_scraper_date', 'scan_logs', ['scraper_name', 'created_at'])


def downgrade() -> None:
    # Drop index first
    op.drop_index('idx_scan_log_scraper_date', table_name='scan_logs')
    
    # Drop table
    op.drop_table('scan_logs')
