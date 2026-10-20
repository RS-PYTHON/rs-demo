#!/usr/bin/env python3

# Copyright 2023-2026 Airbus, CS Group
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Modify the pgstac database after running it."""

import os

from psycopg.errors import UniqueViolation
from pypgstac.pypgstac import PgstacCLI
from smart_open import open

# Make sure that these env vars are set, see: https://stac-utils.github.io/pgstac/pypgstac/
os.environ["PGHOST"]
os.environ["PGPORT"]
os.environ["PGUSER"]
os.environ["PGDATABASE"]
os.environ["PGPASSWORD"]

# They are use by this pypgstac class.
# Print the version number, it will fail if the connection is not OK
pgstac = PgstacCLI()
print(f"Modify the pgstac database version {pgstac.version!r}")

# Connect to the pgstac database
conn = pgstac._db.connect()
with conn.cursor() as cur:

    # Insert hardcoded stac extension urls
    cur.execute(
        """
        INSERT INTO stac_extensions (url)
        VALUES
            ('https://stac-extensions.github.io/eo/v1.1.0/schema.json'),
            ('https://stac-extensions.github.io/sat/v1.2.0/schema.json'),
            ('https://stac-extensions.github.io/projection/v1.1.0/schema.json'),
            ('https://stac-extensions.github.io/processing/v1.2.0/schema.json'),
            ('https://stac-extensions.github.io/product/v0.1.0/schema.json'),
            ('https://stac-extensions.github.io/sar/v1.0.0/schema.json'),
            ('https://stac-extensions.github.io/raster/v1.1.0/schema.json'),
            ('https://stac-extensions.github.io/authentication/v1.1.0/schema.json'),
            ('https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json'),
            ('https://stac-extensions.github.io/timestamps/v1.1.0/schema.json'),
            ('https://stac-extensions.github.io/file/v2.1.0/schema.json')
        ON CONFLICT DO NOTHING;
        """,
    )
    conn.commit()

    # Load the stac extension contents.

    # This does not work, we need to replace 'pgstac._db.query(' by 'cur.execute',
    # I don't know why, so I just copy/paste the code below.
    # pgstac.loadextensions()
    urls = pgstac._db.query(
        """
            SELECT url FROM stac_extensions WHERE content IS NULL;
        """,
    )
    if urls:
        for u in urls:
            url = u[0]
            try:
                with open(url) as f:
                    content = f.read()
                    # pgstac._db.query( # this does not work
                    cur.execute(
                        """
                            UPDATE pgstac.stac_extensions
                            SET content=%s
                            WHERE url=%s
                            ;
                        """,
                        [content, url],
                    )
                    conn.commit()
            except Exception as e:
                print(e)

    # Insert hardcoded queryables
    try:
        for queryable in (
            "eo:snow_cover",
            "sat:absolute_orbit",
            "sat:relative_orbit",
            "processing:level",
            "processing:facility",
            "processing:datetime",
            "processing:version",
            "product:type",
            "product:timeliness",
            "product:timeliness_category",
            "sar:instrument_mode",
            "published",
            "expires",
            "unpublished",
        ):
            cur.execute(
                """
                INSERT INTO queryables (name)
                SELECT %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM queryables WHERE name = %s
                );
                """,
                (queryable, queryable),
            )
        conn.commit()

    # Ignore duplicates
    except UniqueViolation:
        pass

    # Search by externalIds, see rs-server
    # services/catalog/rs_server_catalog/data_management/external_ids.py.
    # pgstac >= 0.10 cannot search inside the externalIds list of objects with
    # the standard CQL2 operators, so rs-server-catalog translates the
    # externalIds searches into the external_ids_contains CQL2 operator, that
    # pgstac translates with the SQL template registered in cql2_ops: a jsonb
    # containment (@>) served by the GIN indexes below. The template must be
    # exactly the indexed expression.
    # The index of queryable_index_template makes pgstac see it as an index of
    # items, so that pgstac.maintain_partitions(dropindexes => true) never
    # tries to drop it from the partitions.
    # The externalIds queryable has no property_path: it only lists externalIds
    # in the queryables.
    # Without parameters, psycopg sends the query as is: %s is not a placeholder.
    cur.execute(
        """
        INSERT INTO queryables (name, definition)
        SELECT 'externalIds', '{
            "title": "externalIds",
            "description": "externalIds",
            "type": "string"
        }'
        WHERE NOT EXISTS (
            SELECT 1 FROM queryables WHERE name = 'externalIds'
        );
        -- The pgstac < 0.10 queryable read the external_ids_tokens() tokens
        UPDATE queryables SET property_path = NULL
        WHERE name = 'externalIds' AND property_path IS NOT NULL;
        DROP FUNCTION IF EXISTS pgstac.external_ids_tokens(jsonb);
        INSERT INTO cql2_ops (op, template)
        VALUES (
            'external_ids_contains',
            '(content->''properties''->''externalIds'' @> %s::jsonb)'
        )
        ON CONFLICT (op) DO UPDATE SET template = EXCLUDED.template;
        CREATE INDEX IF NOT EXISTS queryable_index_template_external_ids_idx
            ON pgstac.queryable_index_template
            USING GIN ((content->'properties'->'externalIds') jsonb_path_ops);
        CREATE INDEX IF NOT EXISTS items_external_ids_idx ON pgstac.items
            USING GIN ((content->'properties'->'externalIds') jsonb_path_ops);
        """,
    )
    conn.commit()

    # Add 'format' and 'pattern' for expires to have better timestamp queries
    try:
        cur.execute(
            """
            UPDATE queryables
            SET definition = '{
                "type": "string",
                "format": "date-time",
                "pattern": "(\\\\+00:00|Z)$"
            }'::jsonb
            WHERE name = 'expires';
            """,
        )
        conn.commit()

    except Exception:
        conn.rollback()
        raise
