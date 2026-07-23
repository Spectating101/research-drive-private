#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd
import requests

BASE="https://arctic-shift.photon-reddit.com"
HERE=Path(__file__).resolve().parent
OUT=Path(os.getenv("REDDIT_SUBSCRIBER_OUT",HERE/"output")); RAW=OUT/"raw"
UA="YZU-stablecoin-research/1.0 (subscriber-history feasibility audit)"


def get_json(path:str,params:dict[str,Any],tries:int=5):
    info={}; err=None
    for n in range(tries):
        started=time.time()
        try:
            r=requests.get(BASE+path,params=params,headers={"User-Agent":UA,"Accept":"application/json"},timeout=90)
            info={"requested_url":r.url,"status_code":r.status_code,"elapsed_seconds":round(time.time()-started,3),"rate_limit_remaining":r.headers.get("X-RateLimit-Remaining")}
            if r.status_code==200:
                try:return r.json(),info
                except ValueError as e:err=f"invalid_json:{e};body={r.text[:300]}"
            else:
                err=f"http_{r.status_code}:{r.text[:300]}"
                if r.status_code not in {429,500,502,503,504}:break
        except Exception as e:
            err=f"{type(e).__name__}:{e}"; info={"requested_url":BASE+path,"status_code":None,"elapsed_seconds":round(time.time()-started,3)}
        time.sleep(min(2**n,12))
    info["error"]=err; return None,info


def dt(v):
    try:
        if isinstance(v,(int,float)) and not isinstance(v,bool):return pd.to_datetime(v,unit="ms" if abs(v)>1e10 else "s",utc=True)
        s=str(v).strip()
        if re.fullmatch(r"\d{4}",s):s+="-01-01"
        elif re.fullmatch(r"\d{4}-\d{2}",s):s+="-01"
        return pd.to_datetime(s,utc=True,errors="raise")
    except:return None


def num(v):
    if v is None or isinstance(v,bool):return None
    try:
        x=float(v); return x if math.isfinite(x) else None
    except:return None


def points(payload):
    out=[]
    def walk(x):
        if isinstance(x,dict):
            d=next((dt(x[k]) for k in ("date","time","timestamp","datetime","created_utc","period","bucket") if k in x and dt(x[k]) is not None),None)
            v=next((num(x[k]) for k in ("value","subscribers","count","y","metric") if k in x and num(x[k]) is not None),None)
            if d is not None and v is not None:out.append((d,v));return
            for k,v0 in x.items():
                d0,v1=dt(k),num(v0)
                if d0 is not None and v1 is not None:out.append((d0,v1))
            for v0 in x.values():
                if isinstance(v0,(dict,list,tuple)):walk(v0)
        elif isinstance(x,(list,tuple)):
            if len(x)>=2 and dt(x[0]) is not None and num(x[1]) is not None:out.append((dt(x[0]),num(x[1])));return
            for v0 in x:walk(v0)
    walk(payload)
    return sorted({(d.isoformat(),float(v)) for d,v in out})


def records(payload):
    if isinstance(payload,list):return [x for x in payload if isinstance(x,dict)]
    if isinstance(payload,dict):
        for k in ("data","result","results","items"):
            if isinstance(payload.get(k),list):return [x for x in payload[k] if isinstance(x,dict)]
        if any(k in payload for k in ("display_name","subreddit","title")):return [payload]
    return []


def gap(months):
    p=sorted(pd.Period(x,freq="M") for x in months)
    return max([((b.year-a.year)*12+b.month-a.month-1) for a,b in zip(p,p[1:])],default=0)


def main():
    OUT.mkdir(parents=True,exist_ok=True);RAW.mkdir(exist_ok=True)
    m=pd.read_csv(HERE/"subreddit_mapping.csv",dtype=str).fillna("")
    cand=[]
    for r in m.to_dict("records"):
        cand.append({**r,"candidate_subreddit":r["subreddit"],"candidate_type":"primary"})
        for a in filter(None,map(str.strip,r["alternate_subreddits"].split("|"))):cand.append({**r,"candidate_subreddit":a,"candidate_type":"alternate"})
    c=pd.DataFrame(cand); subs=sorted(set(c.candidate_subreddit),key=str.lower)
    req=[];meta=[];series=[]
    for i,s in enumerate(subs):
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",s)
        p,info=get_json("/api/subreddits/search",{"subreddit":s,"limit":10});req.append({"candidate_subreddit":s,"endpoint":"metadata",**info})
        (RAW/f"{safe}__metadata.json").write_text(json.dumps(p,indent=2,ensure_ascii=False,default=str))
        rr=records(p); exact=next((x for x in rr if str(x.get("display_name") or x.get("subreddit") or "").lower()==s.lower()),rr[0] if rr else {})
        meta.append({"candidate_subreddit":s,"metadata_found_flag":int(bool(exact)),"returned_display_name":exact.get("display_name") or exact.get("subreddit"),"title":exact.get("title"),"public_description":exact.get("public_description"),"description":exact.get("description"),"current_or_archived_subscribers":exact.get("subscribers"),"subreddit_created_utc":exact.get("created_utc"),"subreddit_id":exact.get("id"),"metadata_retrieved_on":exact.get("retrieved_on")})
        p,info=get_json("/api/time_series",{"key":f"r/{s}/subscribers","precision":"month"});req.append({"candidate_subreddit":s,"endpoint":"time_series",**info})
        (RAW/f"{safe}__subscribers_month.json").write_text(json.dumps(p,indent=2,ensure_ascii=False,default=str))
        for iso,v in points(p):
            t=pd.Timestamp(iso);series.append({"candidate_subreddit":s,"observation_timestamp":iso,"month":t.strftime("%Y-%m"),"subscribers":int(v) if v.is_integer() else v,"source":"Arctic Shift /api/time_series","source_key":f"r/{s}/subscribers","precision_requested":"month"})
        if i+1<len(subs):time.sleep(.35)
    meta=pd.DataFrame(meta); s=pd.DataFrame(series)
    if s.empty:s=pd.DataFrame(columns=["candidate_subreddit","observation_timestamp","month","subscribers","source","source_key","precision_requested"])
    else:
        s["subscribers"]=pd.to_numeric(s.subscribers,errors="coerce");s=s.dropna(subset=["subscribers","month"]).sort_values(["candidate_subreddit","month","observation_timestamp"]).drop_duplicates(["candidate_subreddit","month"],keep="last")
        s["subscriber_change"]=s.groupby("candidate_subreddit").subscribers.diff();s["subscriber_pct_growth"]=s.groupby("candidate_subreddit").subscribers.pct_change(fill_method=None)*100
        s["subscriber_log_growth"]=s.groupby("candidate_subreddit").subscribers.transform(lambda x: x.where(x>0).map(math.log)).diff();s["negative_change_flag"]=(s.subscriber_change<0).astype(int)
    cov=[]
    for sub in subs:
        g=s[s.candidate_subreddit.str.lower()==sub.lower()]
        if g.empty:cov.append({"candidate_subreddit":sub,"observations":0,"first_month":None,"last_month":None,"calendar_span_months":0,"observed_month_share":0,"longest_missing_gap_months":None,"negative_change_count":0,"subscriber_series_found_flag":0,"two_year_coverage_flag":0});continue
        a,b=pd.Period(g.month.min(),freq="M"),pd.Period(g.month.max(),freq="M");span=(b.year-a.year)*12+b.month-a.month+1
        cov.append({"candidate_subreddit":sub,"observations":len(g),"first_month":str(a),"last_month":str(b),"calendar_span_months":span,"observed_month_share":round(len(g)/span,4),"longest_missing_gap_months":gap(g.month),"negative_change_count":int((g.subscriber_change<0).sum()),"subscriber_series_found_flag":1,"two_year_coverage_flag":int(span>=24 and len(g)>=20)})
    cov=pd.DataFrame(cov).merge(meta,on="candidate_subreddit",how="left")
    audit=c.merge(cov,on="candidate_subreddit",how="left");audit["candidate_series_usable_flag"]=((audit.metadata_found_flag.fillna(0).astype(int)==1)&(audit.two_year_coverage_flag.fillna(0).astype(int)==1)).astype(int);audit["manual_semantic_review_required_flag"]=((audit.mapping_confidence!="high")|(audit.candidate_type!="primary")).astype(int)
    expanded=c.merge(s,on="candidate_subreddit",how="inner")
    m.to_csv(OUT/"01_subreddit_mapping_input.csv",index=False);c.to_csv(OUT/"02_subreddit_mapping_candidates.csv",index=False);meta.to_csv(OUT/"03_subreddit_metadata.csv",index=False);s.to_csv(OUT/"04_subreddit_subscribers_monthly.csv",index=False);cov.to_csv(OUT/"05_coverage_by_subreddit.csv",index=False);audit.to_csv(OUT/"06_mapping_and_coverage_audit.csv",index=False);expanded.to_csv(OUT/"07_stablecoin_candidate_subscriber_panel.csv",index=False);pd.DataFrame(req).to_csv(OUT/"08_request_manifest.csv",index=False)
    elig=audit[(audit.candidate_type=="primary")&(audit.mapping_confidence=="high")&(audit.candidate_series_usable_flag==1)]
    summary={"collected_at_utc":datetime.now(timezone.utc).isoformat(),"source":BASE,"mapped_stablecoin_entities":int(m.entity_id.nunique()),"candidate_subreddits_queried":len(subs),"subreddits_with_any_series":int(cov.subscriber_series_found_flag.sum()),"subreddits_with_two_year_coverage":int(cov.two_year_coverage_flag.sum()),"high_confidence_primary_mappings_with_two_year_coverage":int(elig.entity_id.nunique()),"historical_panel_rows":len(s),"expanded_candidate_panel_rows":len(expanded)}
    (OUT/"SUMMARY.json").write_text(json.dumps(summary,indent=2));(OUT/"README.txt").write_text("Historical Reddit subscriber recovery from Arctic Shift. Review mapping and coverage audit before analysis. Shared project/issuer communities are not coin-specific. Raw JSON is retained. Arctic Shift warns that time-series data may not be 100% accurate.\n")
    print(json.dumps(summary,indent=2))

if __name__=="__main__":main()
