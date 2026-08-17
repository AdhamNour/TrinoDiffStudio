WITH diff_data AS (
    SELECT
        COALESCE(p.language_id, o.language_id) AS language_id,
        CASE
            WHEN p.language_id IS NULL THEN 'ONLY_IN_TARGET'
            WHEN o.language_id IS NULL THEN 'ONLY_IN_SOURCE'
            ELSE 'VALUE_MISMATCH'
        END AS row_diff_type,

        -- Source values cast to VARCHAR for uniform unpivoting
        TRIM(CAST(p.extraction_time_slot AS VARCHAR)) AS p_extraction_time_slot,
        TRIM(CAST(CAST(p.extraction_timestamp AS TIMESTAMP(0)) AS VARCHAR)) AS p_extraction_timestamp,
        TRIM(CAST(p.language_key AS VARCHAR)) AS p_language_key,
        TRIM(CAST(p.language_name AS VARCHAR)) AS p_language_name,
        TRIM(CAST(p.updated_by AS VARCHAR)) AS p_updated_by,
        TRIM(CAST(CAST(p.updated_on AS TIMESTAMP(0)) AS VARCHAR)) AS p_updated_on,

        -- Target values cast to VARCHAR for uniform unpivoting
        TRIM(CAST(o.extraction_time_slot AS VARCHAR)) AS o_extraction_time_slot,
        TRIM(CAST(CAST(o.extraction_timestamp AS TIMESTAMP(0)) AS VARCHAR)) AS o_extraction_timestamp,
        TRIM(CAST(o.language_key AS VARCHAR)) AS o_language_key,
        TRIM(CAST(o.language_name AS VARCHAR)) AS o_language_name,
        TRIM(CAST(o.updated_by AS VARCHAR)) AS o_updated_by,
        TRIM(CAST(CAST(o.updated_on AS TIMESTAMP(0)) AS VARCHAR)) AS o_updated_on
    FROM postgres.rdm.ref_app_language p
    FULL OUTER JOIN oracle.rdm.ref_app_language o
        ON p.language_id = o.language_id
    WHERE (
        p.language_id IS NULL
        OR o.language_id IS NULL
        OR ROW(p.extraction_time_slot, p.extraction_timestamp, p.language_key, p.language_name, p.updated_by, p.updated_on)
           IS DISTINCT FROM
           ROW(o.extraction_time_slot, o.extraction_timestamp, o.language_key, o.language_name, o.updated_by, o.updated_on)
    )
),
final_result AS (
    -- VALUE_MISMATCH: expand per-column so each differing column gets its own row
    SELECT
        d.language_id,
        d.row_diff_type,
        u.column_name,
        u.postgres_value,
        u.oracle_value
    FROM diff_data d
    CROSS JOIN UNNEST(
        ARRAY[
            'extraction_time_slot',
            'extraction_timestamp',
            'language_key',
            'language_name',
            'updated_by',
            'updated_on'
        ],
        ARRAY[
            d.p_extraction_time_slot,
            d.p_extraction_timestamp,
            d.p_language_key,
            d.p_language_name,
            d.p_updated_by,
            d.p_updated_on
        ],
        ARRAY[
            d.o_extraction_time_slot,
            d.o_extraction_timestamp,
            d.o_language_key,
            d.o_language_name,
            d.o_updated_by,
            d.o_updated_on
        ]
    ) AS u(column_name, postgres_value, oracle_value)
    WHERE
        d.row_diff_type = 'VALUE_MISMATCH'
        AND u.postgres_value IS DISTINCT FROM u.oracle_value
        AND u.column_name NOT IN ('extraction_timestamp')
        AND u.column_name NOT LIKE '%key'

    UNION ALL

    -- ONLY_IN_TARGET / ONLY_IN_SOURCE: emit a single summary row per missing record
    SELECT
        d.language_id,
        d.row_diff_type,
        CAST(NULL AS VARCHAR) AS column_name,
        CAST(NULL AS VARCHAR) AS postgres_value,
        CAST(NULL AS VARCHAR) AS oracle_value
    FROM diff_data d
    WHERE d.row_diff_type IN ('ONLY_IN_TARGET', 'ONLY_IN_SOURCE', 'ONLY_IN_ORACLE', 'ONLY_IN_POSTGRES')
)
SELECT *
FROM final_result
ORDER BY 1, 2;
