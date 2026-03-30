#!/usr/bin/env python3

# Copyright 2025 Airbus, CS Group
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
            ('https://stac-extensions.github.io/sat/v1.0.0/schema.json'),
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
                with open(url, "r") as f:
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
        cur.execute(
            """
            INSERT INTO queryables (name)
            VALUES
                ('eo:snow_cover'),
                ('sat:absolute_orbit'),
                ('sat:relative_orbit'),
                ('processing:level'),
                ('processing:facility'),
                ('processing:datetime'),
                ('processing:version'),
                ('product:type'),
                ('product:timeliness'),
                ('product:timeliness_category'),
                ('sar:instrument_mode'),
                ('published'),
                ('expires'),
                ('unpublished')
            ON CONFLICT DO NOTHING;
            """,
        )
        conn.commit()

    # Ignore duplicates
    except UniqueViolation:
        pass

    # Add externalIds support for CQL2 search:
    # - Build a token array from item properties + assets externalIds
    # - Use a_overlaps() on the token array for fast matching
    cur.execute(
        """
        CREATE OR REPLACE FUNCTION pgstac.external_ids_tokens(content jsonb) RETURNS jsonb AS $$
            WITH
                prop_ids AS (
                    SELECT scheme, value
                    FROM jsonb_to_recordset(
                        COALESCE(content->'properties'->'externalIds', '[]'::jsonb)
                    ) AS x(scheme text, value text)
                ),
                asset_ids AS (
                    SELECT x.scheme, x.value
                    FROM jsonb_each(COALESCE(content->'assets', '{}'::jsonb)) AS a(key, val)
                    CROSS JOIN LATERAL jsonb_to_recordset(
                        COALESCE(a.val->'externalIds', '[]'::jsonb)
                    ) AS x(scheme text, value text)
                ),
                all_ids AS (
                    SELECT scheme, value FROM prop_ids
                    UNION ALL
                    SELECT scheme, value FROM asset_ids
                ),
                tokens AS (
                    SELECT CASE
                        WHEN scheme IS NOT NULL AND scheme <> '' AND value IS NOT NULL AND value <> ''
                        THEN scheme || ':' || value
                    END AS token
                    FROM all_ids
                    UNION ALL
                    SELECT value FROM all_ids WHERE value IS NOT NULL AND value <> ''
                    UNION ALL
                    SELECT scheme FROM all_ids WHERE scheme IS NOT NULL AND scheme <> ''
                )
            SELECT COALESCE(
                (SELECT jsonb_agg(DISTINCT token) FROM tokens WHERE token IS NOT NULL AND token <> ''),
                '[]'::jsonb
            );
        $$ LANGUAGE SQL IMMUTABLE;
        """,
    )
    conn.commit()

    try:
        cur.execute(
            """
            UPDATE queryables
            SET
                definition = '{"title": "externalIds", "description": "externalIds", "type": "string"}',
                property_path = 'pgstac.external_ids_tokens(content)'
            WHERE name = 'externalIds' AND (collection_ids IS NULL OR collection_ids = '{}'::text[]);
            """,
        )
        conn.commit()
        cur.execute(
            """
            INSERT INTO queryables (name, definition, property_path)
            VALUES (
                'externalIds',
                '{"title": "externalIds", "description": "externalIds", "type": "string"}',
                'pgstac.external_ids_tokens(content)'
            )
            ON CONFLICT DO NOTHING;
            """,
        )
        conn.commit()
    except UniqueViolation:
        pass
