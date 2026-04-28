/**
 * Shopify product/variant cache sync into D1.
 * Pulls a collection page-by-page and upserts into local tables.
 *
 * D1 has a 50-row batch limit per statement, so we chunk inserts.
 */
import type { Env } from "../lib/env.js";
import { Shopify } from "../lib/shopify.js";
import { audit } from "../lib/db.js";
import { unwrapShopifyGid } from "../lib/utils.js";

interface ProductsPage {
  products: {
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
    edges: {
      node: {
        id: string;
        title: string;
        handle: string;
        status: string;
        vendor: string;
        productType: string;
        featuredImage: { url: string } | null;
        variants: {
          edges: {
            node: {
              id: string;
              title: string;
              sku: string | null;
              barcode: string | null;
              price: string;
              compareAtPrice: string | null;
              inventoryQuantity: number | null;
              selectedOptions: { name: string; value: string }[];
              inventoryItem: { id: string } | null;
            };
          }[];
        };
      };
    }[];
  };
}

const COLLECTION_QUERY = `
  query($cursor: String, $collectionId: ID!) {
    collection(id: $collectionId) {
      products(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id title handle status vendor productType
            featuredImage { url }
            variants(first: 100) {
              edges {
                node {
                  id title sku barcode price compareAtPrice inventoryQuantity
                  selectedOptions { name value }
                  inventoryItem { id }
                }
              }
            }
          }
        }
      }
    }
  }
`;

export async function syncCollection(env: Env, collectionShopifyId: string): Promise<{
  products: number;
  variants: number;
}> {
  const shopify = new Shopify(env);
  const collectionGid = collectionShopifyId.startsWith("gid://")
    ? collectionShopifyId
    : `gid://shopify/Collection/${collectionShopifyId}`;

  let cursor: string | null = null;
  let totalProducts = 0;
  let totalVariants = 0;

  do {
    const data = await shopify.graphql<{ collection: ProductsPage }>(COLLECTION_QUERY, {
      cursor,
      collectionId: collectionGid,
    });
    const page = data.collection.products;
    for (const { node: p } of page.edges) {
      await env.DB.prepare(
        `INSERT INTO products
          (shopify_id, shopify_numeric_id, title, handle, status, vendor, product_type,
           collection_id, image_url, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
         ON CONFLICT(shopify_id) DO UPDATE SET
           title = excluded.title,
           handle = excluded.handle,
           status = excluded.status,
           vendor = excluded.vendor,
           product_type = excluded.product_type,
           collection_id = excluded.collection_id,
           image_url = excluded.image_url,
           updated_at = unixepoch()`,
      )
        .bind(
          p.id,
          unwrapShopifyGid(p.id),
          p.title,
          p.handle,
          p.status,
          p.vendor,
          p.productType,
          unwrapShopifyGid(collectionGid),
          p.featuredImage?.url ?? null,
        )
        .run();

      const productRow = await env.DB.prepare("SELECT id FROM products WHERE shopify_id = ?")
        .bind(p.id)
        .first<{ id: number }>();
      if (!productRow) continue;
      totalProducts++;

      for (const { node: v } of p.variants.edges) {
        const opt = v.selectedOptions[0];
        await env.DB.prepare(
          `INSERT INTO variants
            (shopify_id, shopify_numeric_id, product_id, inventory_item_id,
             title, sku, barcode, price, compare_at_price, inventory_quantity,
             option_name, option_value, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
           ON CONFLICT(shopify_id) DO UPDATE SET
             inventory_item_id = excluded.inventory_item_id,
             title = excluded.title,
             sku = excluded.sku,
             barcode = excluded.barcode,
             price = excluded.price,
             compare_at_price = excluded.compare_at_price,
             inventory_quantity = excluded.inventory_quantity,
             option_name = excluded.option_name,
             option_value = excluded.option_value,
             updated_at = unixepoch()`,
        )
          .bind(
            v.id,
            unwrapShopifyGid(v.id),
            productRow.id,
            v.inventoryItem?.id ?? null,
            v.title,
            v.sku,
            v.barcode,
            Number(v.price),
            v.compareAtPrice ? Number(v.compareAtPrice) : null,
            v.inventoryQuantity ?? 0,
            opt?.name ?? null,
            opt?.value ?? null,
          )
          .run();
        totalVariants++;

        // Mirror Shopify-side barcode into our barcodes table for fast lookup.
        if (v.barcode) {
          await env.DB.prepare(
            `INSERT OR IGNORE INTO barcodes (code, variant_shopify_id, product_shopify_id, source)
             VALUES (?, ?, ?, 'import')`,
          )
            .bind(v.barcode, v.id, p.id)
            .run();
        }
      }
    }
    cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (cursor);

  await audit(env, "shopify.sync_collection", {
    entityType: "collection",
    entityId: collectionShopifyId,
    details: { products: totalProducts, variants: totalVariants },
  });

  return { products: totalProducts, variants: totalVariants };
}
