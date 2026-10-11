"""Minute-open diagnostic over latest complete week; no live account access."""
import datetime as dt, hashlib, json
from zoneinfo import ZoneInfo
import replay_paper_plan as hourly
from replay_paper_plan import plan, ROOT

start=int(dt.datetime(2026,10,3,tzinfo=dt.timezone.utc).timestamp())
end=int(dt.datetime(2026,10,10,tzinfo=dt.timezone.utc).timestamp())

def run():
    cache=ROOT/'evaluation/candles_minute_20261003_20261010.json'
    data = hourly.load_candles(cache, start, end, 60)
    # A clean checkout no longer depends on running the 91-day report first.
    hour_cache = ROOT/'evaluation/candles_20260708_20261010.json'
    if not hour_cache.exists():
        hour_cache = ROOT/'evaluation/candles_hourly_minute_warmup_20261003_20261010.json'
    hours = hourly.load_candles(hour_cache, start-60*3600, end, 3600)
    hour_index = hourly.data_index(hours, start-60*3600, end, 3600)
    minute_index = hourly.data_index(data, start, end, 60)
    core=hourly.make_core(); plan.core=core
    core._now=lambda:dt.datetime.fromtimestamp(start,ZoneInfo('America/Puerto_Rico'))
    d=plan.new()
    for t in range(start,end,60):
        core._now=lambda t=t:dt.datetime.fromtimestamp(t,ZoneInfo('America/Puerto_Rico'))
        h=t//3600*3600
        markets={s:core._market_from_closes(s,[hour_index[s][k][4] for k in range(h-60*3600,h,3600)],minute_index[s][t][3]) for s in plan.PRODUCTS}
        plan.apply(d,markets)
    p=d['plan']; slip=core.PAPER_SLIP_PCT/100; fee=core.PAPER_FEE_PCT/100
    liquid=d['cash']+p['allocated_cents']/100+sum(pos['qty']*d['last_prices'][s]*(1-slip)*(1-fee) for s,pos in d['positions'].items())
    report=dict(start='2026-10-03T00:00Z',end_exclusive='2026-10-10T00:00Z',samples_per_symbol=len(data['BTC-USD']),data_sha256=hashlib.sha256(cache.read_bytes()).hexdigest(),engine_sha256=hashlib.sha256((ROOT/'jarvis_paper_plan.py').read_bytes()).hexdigest(),minute=dict(liquidation_value=round(liquid,2),net_return_pct=round((liquid/1000-1)*100,2),realized_net=round(d['realized'],2),closed=p['closed'],wins=p['wins'],win_rate_pct=100*p['wins']/p['closed'] if p['closed'] else None,max_observed_drawdown_pct=round(p['max_drawdown']*100,3),open_positions=len(d['positions']),halted=p['halted']),hourly_same_week=hourly.replay(hours,start,end),limitations=['Only seven days; insufficient sample','Minute opens, not full tick path or actual fills','Historical not prospective out-of-sample','No real order or production state access'])
    report['hourly_data_sha256'] = hashlib.sha256(hour_cache.read_bytes()).hexdigest()
    report['samples_by_symbol'] = {s: len(minute_index[s]) for s in plan.PRODUCTS}
    report['validated_inputs'] = True
    (ROOT/'evaluation/minute_results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':run()
