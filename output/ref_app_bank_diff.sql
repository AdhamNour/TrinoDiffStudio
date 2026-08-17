WITH diff_data AS (
    SELECT
        COALESCE(p.bank_code, o.bank_code) AS bank_code,
        CASE
            WHEN p.bank_code IS NULL THEN 'ONLY_IN_TARGET'
            WHEN o.bank_code IS NULL THEN 'ONLY_IN_SOURCE'
            ELSE 'VALUE_MISMATCH'
        END AS row_diff_type,

        -- Source values cast to VARCHAR for uniform unpivoting
        TRIM(CAST(p.active AS VARCHAR)) AS p_active,
        TRIM(CAST(p.bank_arabic_name AS VARCHAR)) AS p_bank_arabic_name,
        TRIM(CAST(p.bank_english_name AS VARCHAR)) AS p_bank_english_name,
        TRIM(CAST(p.bank_id AS VARCHAR)) AS p_bank_id,
        TRIM(CAST(p.bank_key AS VARCHAR)) AS p_bank_key,
        TRIM(CAST(p.bank_shortname AS VARCHAR)) AS p_bank_shortname,
        TRIM(CAST(CAST(p.created_on AS TIMESTAMP(0)) AS VARCHAR)) AS p_created_on,
        TRIM(CAST(p.extraction_time_slot AS VARCHAR)) AS p_extraction_time_slot,
        TRIM(CAST(CAST(p.extraction_timestamp AS TIMESTAMP(0)) AS VARCHAR)) AS p_extraction_timestamp,
        TRIM(CAST(p.updated_by AS VARCHAR)) AS p_updated_by,
        TRIM(CAST(CAST(p.updated_on AS TIMESTAMP(0)) AS VARCHAR)) AS p_updated_on,

        -- Target values cast to VARCHAR for uniform unpivoting
        TRIM(CAST(o.active AS VARCHAR)) AS o_active,
        TRIM(CAST(o.bank_arabic_name AS VARCHAR)) AS o_bank_arabic_name,
        TRIM(CAST(o.bank_english_name AS VARCHAR)) AS o_bank_english_name,
        TRIM(CAST(o.bank_id AS VARCHAR)) AS o_bank_id,
        TRIM(CAST(o.bank_key AS VARCHAR)) AS o_bank_key,
        TRIM(CAST(o.bank_shortname AS VARCHAR)) AS o_bank_shortname,
        TRIM(CAST(CAST(o.created_on AS TIMESTAMP(0)) AS VARCHAR)) AS o_created_on,
        TRIM(CAST(o.extraction_time_slot AS VARCHAR)) AS o_extraction_time_slot,
        TRIM(CAST(CAST(o.extraction_timestamp AS TIMESTAMP(0)) AS VARCHAR)) AS o_extraction_timestamp,
        TRIM(CAST(o.updated_by AS VARCHAR)) AS o_updated_by,
        TRIM(CAST(CAST(o.updated_on AS TIMESTAMP(0)) AS VARCHAR)) AS o_updated_on
    FROM postgres.rdm.ref_app_bank p
    FULL OUTER JOIN oracle.rdm.ref_app_bank o
        ON p.bank_code = o.bank_code
    WHERE (
        p.bank_code IS NULL
        OR o.bank_code IS NULL
        OR ROW(p.active, p.bank_arabic_name, p.bank_english_name, p.bank_id, p.bank_key, p.bank_shortname, p.created_on, p.extraction_time_slot, p.extraction_timestamp, p.updated_by, p.updated_on)
           IS DISTINCT FROM
           ROW(o.active, o.bank_arabic_name, o.bank_english_name, o.bank_id, o.bank_key, o.bank_shortname, o.created_on, o.extraction_time_slot, o.extraction_timestamp, o.updated_by, o.updated_on)
    )
),
final_result AS (
    -- VALUE_MISMATCH: expand per-column so each differing column gets its own row
    SELECT
        d.bank_code,
        d.row_diff_type,
        u.column_name,
        u.postgres_value,
        u.oracle_value
    FROM diff_data d
    CROSS JOIN UNNEST(
        ARRAY[
            'active',
            'bank_arabic_name',
            'bank_english_name',
            'bank_id',
            'bank_key',
            'bank_shortname',
            'created_on',
            'extraction_time_slot',
            'extraction_timestamp',
            'updated_by',
            'updated_on'
        ],
        ARRAY[
            d.p_active,
            d.p_bank_arabic_name,
            d.p_bank_english_name,
            d.p_bank_id,
            d.p_bank_key,
            d.p_bank_shortname,
            d.p_created_on,
            d.p_extraction_time_slot,
            d.p_extraction_timestamp,
            d.p_updated_by,
            d.p_updated_on
        ],
        ARRAY[
            d.o_active,
            d.o_bank_arabic_name,
            d.o_bank_english_name,
            d.o_bank_id,
            d.o_bank_key,
            d.o_bank_shortname,
            d.o_created_on,
            d.o_extraction_time_slot,
            d.o_extraction_timestamp,
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
        d.bank_code,
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
