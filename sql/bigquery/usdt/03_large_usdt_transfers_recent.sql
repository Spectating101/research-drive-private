-- Recent large Ethereum USDT transfers.
-- Safe default: scans only the last 7 complete UTC days.

DECLARE start_date DATE DEFAULT DATE_SUB(CURRENT_DATE("UTC"), INTERVAL 7 DAY);
DECLARE end_date DATE DEFAULT DATE_SUB(CURRENT_DATE("UTC"), INTERVAL 1 DAY);
DECLARE threshold_usdt BIGNUMERIC DEFAULT 1000000;

SELECT
  block_timestamp,
  DATE(block_timestamp) AS date,
  transaction_hash AS tx_hash,
  event_index AS log_index,
  from_address,
  to_address,
  CAST(quantity AS BIGNUMERIC) / 1000000 AS value_usdt
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers`
WHERE address = '0xdac17f958d2ee523a2206206994597c13d831ec7'
  AND DATE(block_timestamp) BETWEEN start_date AND end_date
  AND CAST(quantity AS BIGNUMERIC) / 1000000 >= threshold_usdt
ORDER BY block_timestamp, event_index;
