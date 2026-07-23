#!/usr/bin/env python3
import os,re,json,time,threading
from pathlib import Path
from datetime import date,datetime,timezone
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
import pandas as pd, requests

H=Path(__file__).resolve().parent; OUT=Path(os.getenv('STABLECOIN_71_OUT',H/'output')); RAW=OUT/'raw'; OUT.mkdir(parents=True,exist_ok=True); RAW.mkdir(exist_ok=True)
KEY=os.getenv('COINGECKO_API_KEY','').strip(); BASE='https://pro-api.coingecko.com/api/v3' if KEY else 'https://api.coingecko.com/api/v3'; HDR={'Accept':'application/json','User-Agent':'YZU-stablecoin-71/1.0'}
if KEY: HDR['x-cg-pro-api-key']=KEY
OV={'celo-dollar':'celo-dollar','celo-euro':'celo-euro','euro-coin':'euro-coin','euro-tether':'euro-tether','fraxfinance':'frax','gyen':'gyen','liquity-usd':'liquity-usd','origin-dollar':'origin-dollar','ripple-usd':'ripple-usd','stasis':'stasis-eurs','terrausd':'terrausd','tether':'tether','usd-coin':'usd-coin','usdd':'usdd','usde':'ethena-usde','usds':'usds','usdtb':'usdtb','vai':'vai','world-liberty-financial-usd':'world-liberty-financial-usd'}
L=threading.Lock(); LAST=0.; GAP=.16 if KEY else 2.05; MAN=[]
def n(s): return re.sub('[^a-z0-9]+','',(s or '').lower())
def num(x):
 try:
  y=float(x); return y if y==y and abs(y)!=float('inf') else None
 except:return None
def get(path,params=None,tries=5):
 global LAST
 for a in range(tries):
  with L:
   w=GAP-(time.monotonic()-LAST)
   if w>0: time.sleep(w)
   LAST=time.monotonic()
  t=time.time()
  try:
   r=requests.get(BASE+path,params=params or {},headers=HDR,timeout=45); info={'path':path,'params':json.dumps(params or {},sort_keys=True),'status_code':r.status_code,'elapsed_seconds':round(time.time()-t,3),'requested_url':r.url}
   if r.status_code==200:
    try:return r.json(),info
    except Exception as e: info['error']=f'json:{e}'
   else:
    info['error']=f'http_{r.status_code}:{r.text[:250]}'
    if r.status_code not in [408,429,500,502,503,504]: return None,info
  except Exception as e: info={'path':path,'params':json.dumps(params or {}),'status_code':None,'elapsed_seconds':round(time.time()-t,3),'requested_url':BASE+path,'error':f'{type(e).__name__}:{e}'}
  time.sleep(min(2**a,20))
 return None,info
def flat(p):
 p=p or {}; c=p.get('community_data') or {}; z=p.get('links') or {}
 return {'reddit_subscribers':num(c.get('reddit_subscribers')),'reddit_average_posts_48h':num(c.get('reddit_average_posts_48h')),'reddit_average_comments_48h':num(c.get('reddit_average_comments_48h')),'reddit_accounts_active_48h':num(c.get('reddit_accounts_active_48h')),'telegram_channel_user_count':num(c.get('telegram_channel_user_count')),'facebook_likes':num(c.get('facebook_likes')),'subreddit_url':z.get('subreddit_url'),'telegram_channel_identifier':z.get('telegram_channel_identifier'),'twitter_screen_name':z.get('twitter_screen_name')}
def dates(start,months):
 t=date.today(); y,m=start,1; out=[]
 while date(y,m,1)<=t:
  if m in months: out.append(date(y,m,1).isoformat())
  m+=1
  if m==13:y+=1;m=1
 return out
def main():
 U=[]
 for p in sorted((H/'input').glob('dimension_chunk_*.json')):U+=json.loads(p.read_text())
 assert len(U)==71
 A,inf=get('/coins/list',{'include_platform':'true','status':'active'} if KEY else {'include_platform':'true'}); MAN.append({'stage':'coin_list_active',**inf}); A=A if isinstance(A,list) else []
 I=[]
 if KEY:
  I,inf=get('/coins/list',{'include_platform':'true','status':'inactive'});MAN.append({'stage':'coin_list_inactive',**inf});I=I if isinstance(I,list) else []
 C=A+I; by={x.get('id'):x for x in C if x.get('id')}; am=defaultdict(set);nm=defaultdict(set);sm=defaultdict(set)
 for x in C:
  cid=x.get('id');
  if not cid:continue
  nm[n(x.get('name'))].add(cid);sm[n(x.get('symbol'))].add(cid)
  for a in (x.get('platforms') or {}).values():
   a=str(a or '').lower()
   if a.startswith('0x') and len(a)==42:am[a].add(cid)
 R=[]
 for r in U:
  cand=[]
  for a in set((r.get('all_ethereum_addresses') or '').lower().split(';')):
   if a in am:
    for cid in sorted(am[a]):cand.append((0,cid,'exact_contract'))
  if r['entity_id'] in OV:cand.append((1,OV[r['entity_id']],'manual_known_coin_id'))
  if r.get('coingecko_id'):cand.append((2,r['coingecko_id'],'existing_dimension_id'))
  for cid in nm.get(n(r['canonical_name']),[]):cand.append((3,cid,'exact_name'))
  s=n(r.get('ticker'))
  if s and len(sm.get(s,set()))==1:cand.append((4,next(iter(sm[s])),'unique_symbol'))
  seen=set(); cand=[x for x in sorted(cand) if not (x[1] in seen or seen.add(x[1]))]; sel=cand[0] if cand else (99,'','unresolved')
  R.append({**r,'resolved_coingecko_id':sel[1],'resolution_method':sel[2],'resolution_candidates':'|'.join(x[1] for x in cand),'coin_list_match_flag':int(sel[1] in by)})
 ids=sorted({r['resolved_coingecko_id'] for r in R if r['resolved_coingecko_id']}); details={}
 def detail(cid):return cid,*get('/coins/'+cid,{'localization':'false','tickers':'false','market_data':'true','community_data':'true','developer_data':'false','sparkline':'false'})
 with ThreadPoolExecutor(max_workers=6 if KEY else 1) as ex:
  for f in as_completed([ex.submit(detail,c) for c in ids]):
   cid,p,inf=f.result();MAN.append({'stage':'current_detail','coin_id':cid,**inf})
   if isinstance(p,dict):details[cid]=p;(RAW/f'current__{cid}.json').write_text(json.dumps(p))
 M=[]
 for r in R:
  p=details.get(r['resolved_coingecko_id'],{});c=flat(p)
  M.append({**r,'detail_fetch_success_flag':int(bool(p)),'coingecko_returned_name':p.get('name'),'coingecko_returned_symbol':p.get('symbol'),'asset_platform_id':p.get('asset_platform_id'),'genesis_date':p.get('genesis_date'),'market_cap_rank':p.get('market_cap_rank'),'categories':'|'.join(p.get('categories') or []),'official_subreddit_url':c['subreddit_url'],'official_telegram_identifier':c['telegram_channel_identifier'],'current_reddit_subscribers':c['reddit_subscribers'],'current_telegram_members':c['telegram_channel_user_count'],'current_reddit_active_48h':c['reddit_accounts_active_48h'],'current_twitter_screen_name':c['twitter_screen_name']})
 probe_dates=dates(2021 if KEY else 2022,[1,4,7,10] if KEY else [7]); P=[]
 def hist(cid,d):return cid,d,*get('/coins/'+cid+'/history',{'date':d,'localization':'false'})
 with ThreadPoolExecutor(max_workers=8 if KEY else 1) as ex:
  for f in as_completed([ex.submit(hist,c,d) for c in ids for d in probe_dates]):
   cid,d,p,inf=f.result();MAN.append({'stage':'historical_probe','coin_id':cid,'date':d,**inf})
   if isinstance(p,dict): P.append({'coingecko_id':cid,'date':d,**{k:v for k,v in flat(p).items() if k not in ['subreddit_url','telegram_channel_identifier','twitter_screen_name']},'source':'CoinGecko /coins/{id}/history'})
 pos=sorted({x['coingecko_id'] for x in P if any(x.get(k) not in [None,0,0.] for k in ['reddit_subscribers','telegram_channel_user_count','reddit_accounts_active_48h'])}); pos=pos if KEY else pos[:12]; MD=[]; md_dates=dates(2021 if KEY else 2023,list(range(1,13)))
 with ThreadPoolExecutor(max_workers=8 if KEY else 1) as ex:
  for f in as_completed([ex.submit(hist,c,d) for c in pos for d in md_dates]):
   cid,d,p,inf=f.result();MAN.append({'stage':'historical_monthly','coin_id':cid,'date':d,**inf})
   if isinstance(p,dict):MD.append({'coingecko_id':cid,'date':d,**{k:v for k,v in flat(p).items() if k not in ['subreddit_url','telegram_channel_identifier','twitter_screen_name']},'source':'CoinGecko /coins/{id}/history'})
 pb=defaultdict(list);mb=defaultdict(list)
 for x in P:pb[x['coingecko_id']].append(x)
 for x in MD:mb[x['coingecko_id']].append(x)
 Q=[]
 for r in M:
  cid=r['resolved_coingecko_id'];pr=pb[cid];mr=mb[cid];rp=[x for x in pr if x.get('reddit_subscribers') not in [None,0,0.]];tp=[x for x in pr if x.get('telegram_channel_user_count') not in [None,0,0.]];ap=[x for x in pr if x.get('reddit_accounts_active_48h') not in [None,0,0.]];rm=[x for x in mr if x.get('reddit_subscribers') not in [None,0,0.]]
  st='monthly_history_recovered' if rm else 'historical_probe_positive' if rp or tp or ap else 'official_social_links_only' if r['official_subreddit_url'] or r['official_telegram_identifier'] else 'resolved_but_no_community_history' if cid else 'unresolved_no_coingecko_id'
  Q.append({'entity_id':r['entity_id'],'canonical_name':r['canonical_name'],'ticker':r['ticker'],'resolved_coingecko_id':cid,'resolution_method':r['resolution_method'],'resolution_status':'resolved_detail_fetched' if r['detail_fetch_success_flag'] else 'resolved_detail_failed' if cid else 'unresolved','official_subreddit_url':r['official_subreddit_url'],'official_telegram_identifier':r['official_telegram_identifier'],'current_reddit_subscribers':r['current_reddit_subscribers'],'current_telegram_members':r['current_telegram_members'],'historical_probe_dates_requested':len(probe_dates) if cid else 0,'historical_probe_rows_returned':len(pr),'historical_reddit_positive_probe_count':len(rp),'historical_telegram_positive_probe_count':len(tp),'historical_reddit_activity_positive_probe_count':len(ap),'historical_monthly_rows_returned':len(mr),'historical_monthly_reddit_positive_count':len(rm),'first_positive_reddit_date':min([x['date'] for x in rp],default=''),'last_positive_reddit_date':max([x['date'] for x in rp],default=''),'community_history_status':st})
 for fn,rows in [('01_stablecoin_71_master.csv',M),('02_historical_community_probe_long.csv',P),('03_historical_community_monthly_long.csv',MD),('04_coverage_report_71.csv',Q),('05_request_manifest.csv',MAN)]:pd.DataFrame(rows).sort_values([c for c in ['entity_id','coingecko_id','date','stage'] if rows and c in rows[0]]).to_csv(OUT/fn,index=False)
 S={'collected_at_utc':datetime.now(timezone.utc).isoformat(),'api_mode':'pro' if KEY else 'public','stablecoins_in_universe':71,'resolved_coingecko_ids':sum(bool(x['resolved_coingecko_id']) for x in M),'current_detail_successes':sum(x['detail_fetch_success_flag'] for x in M),'official_subreddit_links':sum(bool(x['official_subreddit_url']) for x in M),'official_telegram_identifiers':sum(bool(x['official_telegram_identifier']) for x in M),'coins_with_positive_historical_probe':len(set(x['coingecko_id'] for x in P if any(x.get(k) not in [None,0,0.] for k in ['reddit_subscribers','telegram_channel_user_count','reddit_accounts_active_48h']))),'coins_with_monthly_history_recovered':len(set(x['coingecko_id'] for x in MD if x.get('reddit_subscribers') not in [None,0,0.])),'historical_probe_rows':len(P),'monthly_history_rows':len(MD)}
 (OUT/'SUMMARY.json').write_text(json.dumps(S,indent=2));(OUT/'README_FIRST.txt').write_text('Open 04_coverage_report_71.csv first. All 71 stablecoins remain present; missing coverage is explicit.\n');print(json.dumps(S,indent=2))
if __name__=='__main__':main()
