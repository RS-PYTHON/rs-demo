#!/usr/bin/env python3

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
            ('https://stac-extensions.github.io/timestamps/v1.1.0/schema.json')
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
