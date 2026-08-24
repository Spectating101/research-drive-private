-- Recent daily Ethereum USDT flow panel.
-- Safe default: scans only the last 7 complete UTC days.
--
-- Google Blockchain Analytics uses lowercase addresses and monthly partitioning
-- on block_timestamp. Keep the date filter in place for cost control.

DECLARE start_date DATE DEFAULT DATE_SUB(CURRENT_DATE("UTC"), INTERVAL 7 DAY);
DECLARE end_date DATE DEFAULT DATE_SUB(CURRENT_DATE("UTC"), INTERVAL 1 DAY);

SELECT
  DATE(block_timestamp) AS date,
  COUNT(*) AS transfer_count,
  SUM(CAST(quantity AS BIGNUMERIC) / 1000000) AS gross_volume_usdt,
  COUNT(DISTINCT from_address) AS active_senders,
  COUNT(DISTINCT to_address) AS active_receivers,
  COUNT(DISTINCT from_address) + COUNT(DISTINCT to_address) AS sender_receiver_distinct_sum,
  SUM(CASE WHEN CAST(quantity AS BIGNUMERIC) / 1000000 >= 1000000 THEN 1 ELSE 0 END)
    AS large_transfer_count,
  SUM(CASE WHEN CAST(quantity AS BIGNUMERIC) / 1000000 >= 1000000
      THEN CAST(quantity AS BIGNUMERIC) / 1000000
      ELSE 0
    END) AS large_transfer_volume_usdt
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers`
WHERE address = '0xdac17f958d2ee523a2206206994597c13d831ec7'
  AND DATE(block_timestamp) BETWEEN start_date AND end_date
GROUP BY date
ORDER BY date;
