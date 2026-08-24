# IDX retail TA replication study

Generated: 2026-06-12T17:14:13.071708+00:00
OOS holdout: last 25% of panel (`idn_eval_splits.oos_holdout`) | Cost: 25.0bps

## Replication verdicts

| Status | Count |
|--------|-------|
| conditional | 5 |
| reject | 10 |
| replicate | 1 |

## Full playbook results (OOS portfolio)

| Strategy | Jargon | Verdict | n signals | Terminal | Sharpe | Event 5d mean | Hit 5d |
|----------|--------|---------|-----------|----------|--------|---------------|--------|
| bbca_support_rsi | Support + RSI oversold (BBCA) | **conditional** | 88 | 1.163 | 0.411 | 1.58% | 50.8% |
| bbca_support_only | Support saja (BBCA at 60d low) | **reject** | 225 | 0.864 | -0.148 | 0.25% | 42.8% |
| bbca_rsi_oversold | RSI oversold BBCA | **replicate** | 62 | 1.131 | 0.389 | 1.24% | 54.5% |
| banks_rsi_oversold | RSI oversold bank saham | **conditional** | 182 | 1.046 | 0.198 | 0.24% | 44.0% |
| ihsg_support_banks | IHSG support → beli bank | **reject** | 315 | 0.937 | -0.030 | -0.1% | 44.4% |
| ihsg_washout_banks | IHSG washout (drawdown) | **reject** | 104 | 0.888 | -0.176 | 0.2% | 46.1% |
| bluechip_support | Support blue chip | **conditional** | 506 | 0.917 | -0.067 | 0.58% | 50.1% |
| ma20_golden_cross | Golden cross MA20 | **reject** | 654 | 0.578 | -1.060 | -0.05% | 44.7% |
| ma50_golden_cross | Golden cross MA50 | **reject** | 373 | 0.807 | -0.345 | 0.02% | 45.2% |
| ma20_death_cross_avoid | Death cross (fade long) | **reject** | 888 | 0.796 | -0.356 | -0.24% | 44.4% |
| rsi30_bounce | RSI oversold bounce | **conditional** | 932 | 1.069 | 0.242 | 0.23% | 47.5% |
| bollinger_lower | Sentuh Bollinger bawah | **reject** | 917 | 0.600 | -0.861 | 0.18% | 47.7% |
| fib_618_pullback | Fibonacci 61.8% retracement | **reject** | 997 | 0.879 | -0.148 | 0.03% | 45.6% |
| breakout_20d_high | Break resistance / breakout | **reject** | 750 | 0.518 | -1.298 | -0.23% | 44.5% |
| volume_akumulasi | Akumulasi (volume kering lalu  | **reject** | 78 | 0.907 | -0.402 | 0.05% | 39.0% |
| drawdown_dip_volume | Buy the dip + volume (bandar l | **conditional** | 429 | 1.044 | 0.202 | 1.03% | 49.6% |

## Replicate — use these

- **bbca_rsi_oversold**: BBCA RSI(14)<30 only

## Conditional — paper only / narrow scope

- **bbca_support_rsi**: BBCA within 2% of 60d low AND RSI(14)<35
- **banks_rsi_oversold**: Any bank BBCA/BBRI/BMRI RSI<30
- **bluechip_support**: BBCA/BBRI/BMRI/TLKM/ASII within 2% of 40d low
- **rsi30_bounce**: Any liquid name RSI(14)<30
- **drawdown_dip_volume**: 5d return <= -8% AND volume >= 1.4x 20d avg

## Reject — do not systematic trade

- bbca_support_only: Support saja (BBCA at 60d low)
- ihsg_support_banks: IHSG support → beli bank
- ihsg_washout_banks: IHSG washout (drawdown)
- ma20_golden_cross: Golden cross MA20
- ma50_golden_cross: Golden cross MA50
- ma20_death_cross_avoid: Death cross (fade long)
- bollinger_lower: Sentuh Bollinger bawah
- fib_618_pullback: Fibonacci 61.8% retracement
- breakout_20d_high: Break resistance / breakout
- volume_akumulasi: Akumulasi (volume kering lalu naik)

## BBCA support parameter sensitivity (top 5 OOS Sharpe)

- lookback=90d RSI<35 prox=2.0%: Sharpe 0.5199204298669333, terminal 1.2223848744539654x, n=61
- lookback=60d RSI<35 prox=2.0%: Sharpe 0.41087890531923027, terminal 1.1627748493157783x, n=88
- lookback=90d RSI<35 prox=3.0%: Sharpe 0.37495827894536665, terminal 1.1401195270170963x, n=72
- lookback=90d RSI<40 prox=2.0%: Sharpe 0.2622521050520545, terminal 1.0788991089642113x, n=102
- lookback=40d RSI<35 prox=2.0%: Sharpe 0.23357189224247907, terminal 1.064824085286389x, n=95

## Replication checklist

1. Run `python3 scripts/run_idn_retail_replication_study.py` weekly after panel refresh.
2. Trade only **replicate** + **conditional** rules; ignore **reject**.
3. Prefer single-name BBCA support+RSI over broad 50-name RSI scans.
4. Event study n<25 → insufficient; do not promote.
5. Wire top rules into `run_idn_weekly_position_sheet.py` (Lane: retail_ta).

Evidence JSON: `backtests/outputs/idn_retail_replication/latest.json`