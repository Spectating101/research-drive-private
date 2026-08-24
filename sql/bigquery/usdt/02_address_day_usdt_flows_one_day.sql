-- One-day address-level Ethereum USDT flow panel.
-- Safe default: scans one complete UTC day, two days before today.
--
-- This is the first realistic test for address-level research cost/shape.

DECLARE target_date DATE DEFAULT DATE_SUB(CURRENT_DATE("UTC"), INTERVAL 2 DAY);

WITH usdt AS (
  SELECT
    DATE(block_timestamp) AS date,
    from_address,
    to_address,
    CAST(quantity AS BIGNUMERIC) / 1000000 AS value_usdt
  FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers`
  WHERE address = '0xdac17f958d2ee523a2206206994597c13d831ec7'
    AND DATE(block_timestamp) = target_date
),
sent AS (
  SELECT
    date,
    from_address AS address,
    COUNT(*) AS sent_count,
    SUM(value_usdt) AS sent_value_usdt,
    COUNT(DISTINCT to_address) AS sent_counterparties
  FROM usdt
  GROUP BY date, address
),
received AS (
  SELECT
    date,
    to_address AS address,
    COUNT(*) AS received_count,
    SUM(value_usdt) AS received_value_usdt,
    COUNT(DISTINCT from_address) AS received_counterparties
  FROM usdt
  GROUP BY date, address
)
SELECT
  COALESCE(s.date, r.date) AS date,
  COALESCE(s.address, r.address) AS address,
  COALESCE(sent_count, 0) AS sent_count,
  COALESCE(received_count, 0) AS received_count,
  COALESCE(sent_value_usdt, 0) AS sent_value_usdt,
  COALESCE(received_value_usdt, 0) AS received_value_usdt,
  COALESCE(received_value_usdt, 0) - COALESCE(sent_value_usdt, 0) AS net_value_usdt,
  COALESCE(sent_counterparties, 0) AS sent_counterparties,
  COALESCE(received_counterparties, 0) AS received_counterparties
FROM sent s
FULL OUTER JOIN received r
  ON s.date = r.date
 AND s.address = r.address
ORDER BY date, ABS(net_value_usdt) DESC
LIMIT 10000;
