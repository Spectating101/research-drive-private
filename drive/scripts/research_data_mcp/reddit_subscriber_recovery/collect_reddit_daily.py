#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

BASE="https://arctic-shift.photon-reddit.com"
HERE=Path(__file__).resolve().parent
OUT=Path(os.getenv("REDDIT_DAILY_OUT",HERE/"daily_output"));RAW=OUT/"raw_daily"
UA="YZU-stablecoin-research/1.0 (reviewed daily subscriber-history audit)"


def get(sub):
    params={"key":f"r/{sub}/subscribers","precision":"day"}; last=None; info={}
    for n in range(5):
        try:
            r=requests.get(BASE+"/api/time_series",params=params,headers={"User-Agent":UA,"Accept":"application/json"},timeout=120)
            info={"subreddit":sub,"url":r.url,"status_code":r.status_code,"rate_limit_remaining":r.headers.get("X-RateLimit-Remaining")}
            if r.status_code==200:return r.json(),info
            last=f"http_{r.status_code}:{r.text[:300]}"
            if r.status_code not in {429,500,502,503,504}:break
        except Exception as e:last=f"{type(e).__name__}:{e}"
        time.sleep(min(2**n,12))
    info["error"]=last;return None,info


def parse(payload):
    data=payload.get("data",[]) if isinstance(payload,dict) else payload if isinstance(payload,list) else []
    rows=[]
    for x in data:
        if isinstance(x,dict):date=x.get("date");value=x.get("value")
        elif isinstance(x,(list,tuple)) and len(x)>=2:date,value=x[0],x[1]
        else:continue
        try:
            t=pd.to_datetime(date,unit="ms" if abs(float(date))>1e10 else "s",utc=True) if isinstance(date,(int,float)) else pd.to_datetime(date,utc=True)
            v=float(value)
            if math.isfinite(v):rows.append((t,v))
        except:continue
    return rows


def longest_block(months):
    ps=sorted(set(pd.Period(x,freq="M") for x in months))
    if not ps:return None,None,0
    best=(ps[0],ps[0],1);start=prev=ps[0]
    for p in ps[1:]:
        delta=(p.year-prev.year)*12+p.month-prev.month
        if delta==1:prev=p
        else:
            n=(prev.year-start.year)*12+prev.month-start.month+1
            if n>best[2]:best=(start,prev,n)
            start=prev=p
    n=(prev.year-start.year)*12+prev.month-start.month+1
    if n>best[2]:best=(start,prev,n)
    return str(best[0]),str(best[1]),best[2]


def main():
    OUT.mkdir(parents=True,exist_ok=True);RAW.mkdir(exist_ok=True)
    mp=pd.read_csv(HERE/"reviewed_subreddits.csv",dtype=str).fillna("")
    daily=[];manifest=[]
    for i,sub in enumerate(mp.subreddit):
        payload,info=get(sub);manifest.append(info)
        (RAW/f"{sub}__daily.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False,default=str))
        for t,v in parse(payload):daily.append({"subreddit":sub,"date":t.strftime("%Y-%m-%d"),"month":t.strftime("%Y-%m"),"subscribers_daily_mean":v,"source_key":f"r/{sub}/subscribers","precision":"day"})
        if i+1<len(mp):time.sleep(.5)
    d=pd.DataFrame(daily)
    if d.empty:raise RuntimeError("No daily subscriber observations parsed")
    d=d.sort_values(["subreddit","date"]).drop_duplicates(["subreddit","date"],keep="last")
    monthly=(d.groupby(["subreddit","month"],as_index=False)
             .agg(monthly_mean_subscribers=("subscribers_daily_mean","mean"),
                  monthly_median_subscribers=("subscribers_daily_mean","median"),
                  month_end_subscribers=("subscribers_daily_mean","last"),
                  last_observed_date=("date","last"),
                  observed_days_in_month=("date","nunique")))
    monthly["previous_month"]=monthly.groupby("subreddit").month.shift()
    monthly["previous_month_end_subscribers"]=monthly.groupby("subreddit").month_end_subscribers.shift()
    def mdiff(r):
        if pd.isna(r.previous_month):return pd.NA
        a,b=pd.Period(r.previous_month,freq="M"),pd.Period(r.month,freq="M")
        return (b.year-a.year)*12+b.month-a.month
    monthly["months_since_previous_observation"]=monthly.apply(mdiff,axis=1).astype("Int64")
    monthly["adjacent_month_flag"]=(monthly.months_since_previous_observation==1).astype(int)
    monthly["interval_subscriber_change"]=monthly.month_end_subscribers-monthly.previous_month_end_subscribers
    monthly["interval_log_change"]=monthly.apply(lambda r: math.log(r.month_end_subscribers)-math.log(r.previous_month_end_subscribers) if pd.notna(r.previous_month_end_subscribers) and r.month_end_subscribers>0 and r.previous_month_end_subscribers>0 else pd.NA,axis=1)
    monthly["monthlyized_interval_log_growth"]=monthly.interval_log_change/monthly.months_since_previous_observation
    monthly["adjacent_month_log_growth"]=monthly.interval_log_change.where(monthly.adjacent_month_flag==1)
    monthly["adjacent_month_pct_growth"]=(monthly.month_end_subscribers/monthly.previous_month_end_subscribers-1).mul(100).where(monthly.adjacent_month_flag==1)
    coverage=[]
    for sub,g in monthly.groupby("subreddit"):
        a,b=pd.Period(g.month.min(),freq="M"),pd.Period(g.month.max(),freq="M");span=(b.year-a.year)*12+b.month-a.month+1
        bs,be,bn=longest_block(g.month)
        coverage.append({"subreddit":sub,"first_month":str(a),"last_month":str(b),"observed_months":len(g),"calendar_span_months":span,"observed_month_share":round(len(g)/span,4),"adjacent_growth_observations":int(g.adjacent_month_flag.sum()),"longest_contiguous_block_start":bs,"longest_contiguous_block_end":be,"longest_contiguous_block_months":bn,"median_observed_days_per_month":float(g.observed_days_in_month.median()),"minimum_observed_days_per_month":int(g.observed_days_in_month.min()),"maximum_observed_days_per_month":int(g.observed_days_in_month.max())})
    coverage=pd.DataFrame(coverage).merge(mp,on="subreddit",how="left")
    community_panel=monthly.merge(mp,on="subreddit",how="left")
    d.to_csv(OUT/"01_daily_subscriber_observations.csv",index=False)
    monthly.to_csv(OUT/"02_month_end_subscriber_panel.csv",index=False)
    coverage.to_csv(OUT/"03_reviewed_coverage.csv",index=False)
    mp.to_csv(OUT/"04_reviewed_mapping.csv",index=False)
    community_panel.to_csv(OUT/"05_reviewed_community_panel.csv",index=False)
    pd.DataFrame(manifest).to_csv(OUT/"06_request_manifest.csv",index=False)
    summary={"collected_at_utc":datetime.now(timezone.utc).isoformat(),"reviewed_subreddits":int(mp.subreddit.nunique()),"subreddits_with_daily_data":int(d.subreddit.nunique()),"daily_rows":len(d),"monthly_rows":len(monthly),"adjacent_month_growth_rows":int(monthly.adjacent_month_flag.sum()),"communities_with_24_month_contiguous_block":int((coverage.longest_contiguous_block_months>=24).sum()),"communities_with_36_month_contiguous_block":int((coverage.longest_contiguous_block_months>=36).sum())}
    (OUT/"SUMMARY.json").write_text(json.dumps(summary,indent=2));(OUT/"README.txt").write_text("Reviewed Reddit subscriber history. Values are Arctic Shift daily aggregates derived from archived Reddit metadata. The month-end field is the last observed daily aggregate in each month, not an official Reddit month-end snapshot. Growth across gaps is kept as interval/monthlyized growth; adjacent-month growth is populated only when consecutive calendar months are observed. Project and issuer mappings must be interpreted at their documented scope.\n")
    print(json.dumps(summary,indent=2))

if __name__=="__main__":main()
