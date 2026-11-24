"""add commerce catalog

Revision ID: ebb479ab376c
Revises: bddc69df7d01
Create Date: 2026-11-23 21:04:21.650444

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ebb479ab376c'
down_revision = 'bddc69df7d01'
branch_labels = None
depends_on = None


def upgrade():

    op.create_table('product_category',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_category_slug'), 'product_category', ['slug'], unique=True)
    op.create_table('product',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('description', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=True),
    sa.Column('image_file_ids', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('seo_title', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('seo_description', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['product_category.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_category_id'), 'product', ['category_id'], unique=False)
    op.create_index(op.f('ix_product_slug'), 'product', ['slug'], unique=True)
    op.create_index(op.f('ix_product_status'), 'product', ['status'], unique=False)
    op.create_index(op.f('ix_product_type'), 'product', ['type'], unique=False)
    op.create_table('product_option',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('values', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['product.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product_id', 'name', name='uq_option_name')
    )
    op.create_index(op.f('ix_product_option_product_id'), 'product_option', ['product_id'], unique=False)
    op.create_table('product_variant',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('sku', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('option_values', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('options_key', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
    sa.Column('stock', sa.Integer(), nullable=True),
    sa.Column('file_id', sa.Uuid(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.CheckConstraint('stock IS NULL OR stock >= 0', name='ck_variant_stock'),
    sa.ForeignKeyConstraint(['file_id'], ['file.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['product.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product_id', 'options_key', name='uq_variant_options')
    )
    op.create_index(op.f('ix_product_variant_file_id'), 'product_variant', ['file_id'], unique=False)
    op.create_index(op.f('ix_product_variant_product_id'), 'product_variant', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_variant_sku'), 'product_variant', ['sku'], unique=True)
    op.create_table('service_slot',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint('capacity >= 1', name='ck_slot_capacity'),
    sa.CheckConstraint('ends_at > starts_at', name='ck_slot_window'),
    sa.ForeignKeyConstraint(['product_id'], ['product.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product_id', 'starts_at', 'ends_at', name='uq_slot_window')
    )
    op.create_index(op.f('ix_service_slot_product_id'), 'service_slot', ['product_id'], unique=False)
    op.create_index(op.f('ix_service_slot_starts_at'), 'service_slot', ['starts_at'], unique=False)
    op.create_table('variant_price',
    sa.Column('variant_id', sa.Uuid(), nullable=False),
    sa.Column('currency', sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.CheckConstraint('amount > 0', name='ck_variant_price_amount'),
    sa.ForeignKeyConstraint(['variant_id'], ['product_variant.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('variant_id', 'currency')
    )



def downgrade():

    op.drop_table('variant_price')
    op.drop_index(op.f('ix_service_slot_starts_at'), table_name='service_slot')
    op.drop_index(op.f('ix_service_slot_product_id'), table_name='service_slot')
    op.drop_table('service_slot')
    op.drop_index(op.f('ix_product_variant_sku'), table_name='product_variant')
    op.drop_index(op.f('ix_product_variant_product_id'), table_name='product_variant')
    op.drop_index(op.f('ix_product_variant_file_id'), table_name='product_variant')
    op.drop_table('product_variant')
    op.drop_index(op.f('ix_product_option_product_id'), table_name='product_option')
    op.drop_table('product_option')
    op.drop_index(op.f('ix_product_type'), table_name='product')
    op.drop_index(op.f('ix_product_status'), table_name='product')
    op.drop_index(op.f('ix_product_slug'), table_name='product')
    op.drop_index(op.f('ix_product_category_id'), table_name='product')
    op.drop_table('product')
    op.drop_index(op.f('ix_product_category_slug'), table_name='product_category')
    op.drop_table('product_category')
