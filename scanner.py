from __future__ import annotations
import os, time
from dataclasses import dataclass, asdict
from typing import Any
import numpy as np
import pandas as pd
import requests

PRODUCT_TYPE='usdt-futures'; REQUEST_TIMEOUT=20
SCAN_TF={'4h':'4H','1h':'1H','15m':'15m','5m':'5m'}
COACH_TF={**SCAN_TF,'1m':'1m'}
CANDLE_LIMIT=int(os.getenv('CANDLE_LIMIT','220'))
MAX_MARKETS=int(os.getenv('MAX_MARKETS','100'))
MIN_VOLUME=float(os.getenv('MIN_24H_USDT_VOLUME','1000000'))
s=requests.Session(); s.headers.update({'User-Agent':'CryptoHunters-3.0'})

def get_json(url,params=None):
 r=s.get(url,params=params,timeout=REQUEST_TIMEOUT); r.raise_for_status(); p=r.json()
 if isinstance(p,dict) and p.get('code') not in (None,'00000'): raise RuntimeError(p.get('msg','API error'))
 return p

def normalize_symbol(symbol: str) -> str:
 raw = str(symbol or '').upper().strip()
 for token in ('/', '-', '_', ' ', ':'):
  raw = raw.replace(token, '')
 for suffix in ('PERPETUAL', 'PERP'):
  if raw.endswith(suffix): raw = raw[:-len(suffix)]
 if raw.endswith('USDTUSDT'): raw = raw[:-4]
 if not raw.endswith('USDT'): raw += 'USDT'
 return raw

def ema(x,n): return x.ewm(span=n,adjust=False,min_periods=n).mean()
def rsi(x,n=14):
 d=x.diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
 ag=g.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); al=l.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
 return (100-100/(1+ag/al.replace(0,np.nan))).fillna(50)
def macd(x):
 line=ema(x,12)-ema(x,26); sig=ema(line,9); return line,sig,line-sig
def atr(df,n=14):
 pc=df.close.shift(1); tr=pd.concat([df.high-df.low,(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
 return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
def normalize(rows):
 df=pd.DataFrame(rows,columns=['timestamp','open','high','low','close','volume','quote_volume'])
 for c in df.columns: df[c]=pd.to_numeric(df[c],errors='coerce')
 return df.dropna().drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)

class Bitget:
 name='Bitget USDT Perpetual'
 def markets(self):
  p=get_json('https://api.bitget.com/api/v2/mix/market/tickers',{'productType':PRODUCT_TYPE}); out=[]
  for t in p.get('data',[]):
   symbol=str(t.get('symbol','')); vol=float(t.get('usdtVolume') or t.get('quoteVolume') or 0)
   if symbol.endswith('USDT') and vol>=MIN_VOLUME:
    out.append({'symbol':symbol,'volume24h_usdt':vol,'change24h_pct':float(t.get('change24h') or 0)*100})
  return sorted(out,key=lambda x:x['volume24h_usdt'],reverse=True)[:MAX_MARKETS]
 def candles(self,symbol,granularity):
  symbol = normalize_symbol(symbol)
  p=get_json('https://api.bitget.com/api/v2/mix/market/candles',{'symbol':symbol,'productType':PRODUCT_TYPE,'granularity':granularity,'limit':CANDLE_LIMIT,'kLineType':'MARKET'})
  rows = p.get('data',[])
  if not rows:
   raise RuntimeError(f'{symbol} was not found on Bitget USDT perpetuals or returned no candle data')
  return normalize(rows)
 def ticker(self, symbol):
  symbol = normalize_symbol(symbol)
  p=get_json('https://api.bitget.com/api/v2/mix/market/ticker',{'symbol':symbol,'productType':PRODUCT_TYPE})
  data = p.get('data') or []
  item = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else {}
  price = float(item.get('lastPr') or item.get('last') or item.get('close') or 0)
  if price <= 0:
   raise RuntimeError(f'{symbol} was not found on Bitget USDT perpetuals')
  return price

@dataclass
class F:
 price:float; ema9:float; ema21:float; ema50:float; rsi:float; macd:float; signal:float; hist:float; prev_hist:float
 rvol:float; extension:float; bull_cross:bool; bear_cross:bool; rising:bool; falling:bool; bull:bool; bear:bool; atr:float

def feat(df,live=False,ema_fast=9,ema_mid=21,ema_slow=50):
 if len(df)<70:return None
 c=df.close; e9,e21,e50=ema(c,ema_fast),ema(c,ema_mid),ema(c,ema_slow); rr=rsi(c); ml,ms,mh=macd(c); aa=atr(df)
 rv=df.quote_volume/df.quote_volume.rolling(20).mean().replace(0,np.nan); i=len(df)-1 if live else len(df)-2; p=i-1
 vals=[e9.iloc[i],e21.iloc[i],e50.iloc[i],rr.iloc[i],ml.iloc[i],ms.iloc[i],mh.iloc[i],rv.iloc[i],aa.iloc[i]]
 if any(pd.isna(v) for v in vals):return None
 price=float(c.iloc[i])
 return F(price,float(e9.iloc[i]),float(e21.iloc[i]),float(e50.iloc[i]),float(rr.iloc[i]),float(ml.iloc[i]),float(ms.iloc[i]),float(mh.iloc[i]),float(mh.iloc[p]),float(rv.iloc[i]),abs(price/float(e21.iloc[i])-1)*100,bool(e9.iloc[i]>e21.iloc[i] and e9.iloc[p]<=e21.iloc[p]),bool(e9.iloc[i]<e21.iloc[i] and e9.iloc[p]>=e21.iloc[p]),bool(e9.iloc[i]>e9.iloc[i-3] and e21.iloc[i]>e21.iloc[i-3]),bool(e9.iloc[i]<e9.iloc[i-3] and e21.iloc[i]<e21.iloc[i-3]),bool(e9.iloc[i]>e21.iloc[i]>e50.iloc[i]),bool(e9.iloc[i]<e21.iloc[i]<e50.iloc[i]),float(aa.iloc[i]))

def state(f,side):
 long=side=='LONG'
 return {'structure':f.bull if long else f.bear,'slope':f.rising if long else f.falling,'macd':f.macd>f.signal if long else f.macd<f.signal,'strength':f.hist>f.prev_hist if long else f.hist<f.prev_hist,'rsi':f.rsi>=50 if long else f.rsi<=50,'cross':f.bull_cross if long else f.bear_cross}

def score_stage(f,side,stage):
 q=state(f,side); pts=0; warns=[]
 if stage=='4h': pts=11*q['structure']+5*q['slope']+5*q['macd']+4*q['rsi']; cap=25
 elif stage=='1h':
  pts=9*q['structure']+4*q['slope']+6*q['macd']+3*q['strength']+3*((50<=f.rsi<=70) if side=='LONG' else (30<=f.rsi<=50)); cap=25
  if (f.rsi>72 if side=='LONG' else f.rsi<28):warns.append('1H RSI stretched')
 elif stage=='15m':
  pts=8*q['structure']+6*q['cross']+5*q['macd']+4*q['strength']+3*((52<=f.rsi<=68) if side=='LONG' else (32<=f.rsi<=48))+2*(f.rvol>=1.35); cap=30
  if f.extension>5:pts-=6;warns.append(f'15M extended {f.extension:.1f}% from EMA21')
 else:
  pts=(6*q['cross'] if q['cross'] else 4*q['structure'])+(5 if q['macd'] and q['strength'] else 3*q['macd'])+4*((50<=f.rsi<=66) if side=='LONG' else (34<=f.rsi<=50))+3*(f.rvol>=1.35); cap=20
  if f.extension>2.5:pts-=5;warns.append(f'5M extended {f.extension:.1f}% from EMA21')
 return max(0,min(cap,float(pts))),warns

def status(total,a,b,c,d,w):
 if a<15 or b<14:return 'SKIP — higher timeframe conflict'
 if c<17:return 'WATCH — setup incomplete'
 if d<11:return 'WAIT — no 5M entry yet'
 if w and total<85:return 'CAUTION — extended'
 return 'READY — verify chart/risk' if total>=82 else 'WATCH — developing'

def scan(ema_fast=9, ema_mid=21, ema_slow=50, sync_window=3):
 ex=Bitget(); rows=[]
 for m in ex.markets():
  try:
   ff={k:feat(ex.candles(m['symbol'],v), ema_fast=ema_fast, ema_mid=ema_mid, ema_slow=ema_slow) for k,v in SCAN_TF.items()}
   if any(v is None for v in ff.values()):continue
   for side in ('LONG','SHORT'):
    a,w1=score_stage(ff['4h'],side,'4h'); b,w2=score_stage(ff['1h'],side,'1h'); c,w3=score_stage(ff['15m'],side,'15m'); d,w4=score_stage(ff['5m'],side,'5m'); total=round(a+b+c+d,1); w=w1+w2+w3+w4
    sync_bonus = 5 if ((side=='LONG' and ff['15m'].macd>ff['15m'].signal and ff['15m'].rsi>=50) or (side=='SHORT' and ff['15m'].macd<ff['15m'].signal and ff['15m'].rsi<=50)) else 0
    total=min(100, round(total+sync_bonus,1))
    rows.append({'symbol':m['symbol'],'side':side,'score':total,'grade':'A+' if total>=90 else 'A' if total>=82 else 'B' if total>=74 else 'C' if total>=65 else 'D','status':status(total,a,b,c,d,w),'price':ff['5m'].price,'trend_4h':a,'confirm_1h':b,'setup_15m':c,'entry_5m':d,'rsi_15m':ff['15m'].rsi,'rsi_5m':ff['5m'].rsi,'extension_5m_pct':ff['5m'].extension,'volume24h_usdt':m['volume24h_usdt'],'change24h_pct':m['change24h_pct'],'ema_alignment': 'BULL' if ff['15m'].bull else 'BEAR' if ff['15m'].bear else 'MIXED', 'rsi_macd_sync': bool(sync_bonus), 'warnings':'; '.join(w)})
   time.sleep(.06)
  except Exception as e: print('Skipped',m['symbol'],e)
 return pd.DataFrame(rows).sort_values(['score','volume24h_usdt'],ascending=[False,False]).reset_index(drop=True) if rows else pd.DataFrame()

def validate_symbol(symbol: str) -> dict[str, Any]:
 normalized = normalize_symbol(symbol)
 ex = Bitget()
 price = ex.ticker(normalized)
 # Confirm candle history too, because the coach requires it.
 candles = ex.candles(normalized, '1m')
 if len(candles) < 70:
  raise RuntimeError(f'{normalized} exists on Bitget, but does not have enough candle history for Hunter')
 return {'symbol': normalized, 'price': price, 'source': ex.name, 'status': 'LIVE'}

def analyze_symbol(symbol,side,entry_price=None,ema_fast=9,ema_mid=21,ema_slow=50,sync_window=3):
 side=side.upper(); symbol=normalize_symbol(symbol); ex=Bitget()
 ff={k:feat(ex.candles(symbol,v),live=(k=='1m'),ema_fast=ema_fast,ema_mid=ema_mid,ema_slow=ema_slow) for k,v in COACH_TF.items()}
 if any(v is None for v in ff.values()):raise RuntimeError('Not enough candle data')
 a,w1=score_stage(ff['4h'],side,'4h'); b,w2=score_stage(ff['1h'],side,'1h'); c,w3=score_stage(ff['15m'],side,'15m'); d,w4=score_stage(ff['5m'],side,'5m'); total=round(a+b+c+d,1)
 micro=state(ff['1m'],side); mscore=25*micro['structure']+20*micro['slope']+20*micro['macd']+15*micro['strength']+10*micro['rsi']+10*micro['cross']
 opposite=state(ff['1m'],'SHORT' if side=='LONG' else 'LONG'); reversal=sum(opposite.values())>=4; chase=ff['5m'].extension>2.5 or ff['15m'].extension>5
 if a<15 or b<14: action,risk,head='AVOID','HIGH','Higher timeframes conflict with this direction.'
 elif reversal and mscore<60: action,risk,head='EXIT / DO NOT ENTER','HIGH','The 1-minute structure is moving against the planned trade.'
 elif chase: action,risk,head='WAIT FOR PULLBACK','ELEVATED','Direction may be valid, but the entry is extended.'
 elif c>=17 and d>=11 and mscore>=60: action,risk,head='ENTRY WINDOW OPEN','MODERATE','Higher timeframes, 5M entry, and 1M momentum agree.'
 elif c>=17: action,risk,head='WAIT','MODERATE','Setup exists, but the 1-minute trigger has not confirmed.'
 else: action,risk,head='WATCH','MODERATE','The setup is still developing.'
 price=ff['1m'].price; sign=1 if side=='LONG' else -1; dist=max(ff['5m'].atr*.85,price*.0025); pnl=None if not entry_price else (price/entry_price-1)*100*sign
 notes=[head,f'4H/1H: {a+b:.0f}/50 • 15M: {c:.0f}/30 • 5M: {d:.0f}/20.',('1M MACD agrees and strengthens.' if micro['macd'] and micro['strength'] else '1M momentum is not fully confirmed.'),('Do not chase this move.' if chase else 'Entry is not flagged as overextended.')]
 if pnl is not None:notes.append(f'Move from your entry: {pnl:+.2f}% before leverage and fees.')
 bull_score = round((25 if ff['15m'].bull else 0) + (20 if ff['15m'].macd>ff['15m'].signal else 0) + (15 if ff['15m'].hist>ff['15m'].prev_hist else 0) + (15 if ff['15m'].rsi>=50 else 0) + (25 if ff['5m'].bull else 0), 1)
 bear_score = round((25 if ff['15m'].bear else 0) + (20 if ff['15m'].macd<ff['15m'].signal else 0) + (15 if ff['15m'].hist<ff['15m'].prev_hist else 0) + (15 if ff['15m'].rsi<=50 else 0) + (25 if ff['5m'].bear else 0), 1)
 return {'symbol':symbol,'side':side,'price':price,'data_source':ex.name,'connection_status':'LIVE','scanner_score':total,'micro_score':mscore,'bull_score':bull_score,'bear_score':bear_score,'ema_settings':{'fast':ema_fast,'mid':ema_mid,'slow':ema_slow},'sync_window':sync_window,'action':action,'risk':risk,'headline':head,'commentary':notes,'stop_reference':price-sign*dist,'target1':price+sign*dist,'target2':price+sign*dist*1.75,'pnl_pct':pnl,'rsi':{k:ff[k].rsi for k in ('4h','1h','15m','5m','1m')},'warnings':w1+w2+w3+w4}


def send_twilio_sms(text: str) -> None:
    """
    Optional SMS alert through Twilio.
    Required environment variables:
      TWILIO_ACCOUNT_SID
      TWILIO_AUTH_TOKEN
      TWILIO_FROM_NUMBER
      ALERT_PHONE_NUMBER
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    to_number = os.getenv("ALERT_PHONE_NUMBER", "").strip()

    if not all([account_sid, auth_token, from_number, to_number]):
        return

    response = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        auth=(account_sid, auth_token),
        data={"From": from_number, "To": to_number, "Body": text},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()


def send_position_alert(text: str, use_telegram: bool = True, use_sms: bool = False) -> None:
    errors = []
    if use_telegram:
        try:
            send_telegram(text)
        except Exception as exc:
            errors.append(f"Telegram: {exc}")
    if use_sms:
        try:
            send_twilio_sms(text)
        except Exception as exc:
            errors.append(f"SMS: {exc}")
    if errors:
        raise RuntimeError(" | ".join(errors))
