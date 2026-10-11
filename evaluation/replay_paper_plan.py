"""Offline hourly diagnostic; no app import, credentials, storage or real orders.
Public candle download is separate from replay. Existing pure core functions are
loaded by AST so their accounting/indicators remain identical to this checkout.
"""
import subprocess
import ast, datetime as dt, hashlib, json, math, sys, types, urllib.request, concurrent.futures
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import jarvis_paper_plan as plan
NAMES = {'_paper_new', '_paper_trade', '_paper_buy', '_sma', '_rsi', '_market_from_closes'}

def candle_index(rows, start, end, granularity):
    """Validate downloads AND cached inputs before deriving indicators or results."""
    if granularity not in (60, 3600) or start >= end or start % granularity or end % granularity:
        raise ValueError('invalid candle interval')
    if not isinstance(rows, list):
        raise ValueError('candles must be a list')
    index = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            raise ValueError('invalid candle shape')
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in row):
            raise ValueError('candle values must be finite numbers')
        t, low, high, opening, close, volume = row
        if t != int(t) or t % granularity:
            raise ValueError('unaligned candle timestamp')
        if low <= 0 or high < low or not low <= opening <= high or not low <= close <= high or volume < 0:
            raise ValueError('invalid candle prices or volume')
        t = int(t)
        if t in index:
            raise ValueError('duplicate candle timestamp')
        index[t] = row
    required = set(range(start, end, granularity))
    if not required.issubset(index):
        raise ValueError(f'missing {len(required - index.keys())} candles')
    # Longer caches can support subperiods, but future bars never enter this index.
    return {t: index[t] for t in sorted(required)}


def data_index(data, start, end, granularity):
    if not isinstance(data, dict) or set(data) != set(plan.PRODUCTS):
        raise ValueError('missing or unexpected candle products')
    return {s: candle_index(data[s], start, end, granularity) for s in plan.PRODUCTS}


def load_candles(cache, start, end, granularity):
    """Only public market data; corrupt caches fail closed and are never replaced."""
    cache = Path(cache)
    if cache.exists():
        data = json.loads(cache.read_text())
        data_index(data, start, end, granularity)
        return data
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        data = dict(zip(plan.PRODUCTS, pool.map(
            lambda s: download(s, start, end, granularity), plan.PRODUCTS)))
    data_index(data, start, end, granularity)
    cache.write_text(json.dumps(data, separators=(',', ':')))
    return data

def make_core():
    tree = ast.parse((ROOT/'main.py').read_text())
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
    assert {n.name for n in body} == NAMES
    core = types.ModuleType('offline_paper_core')
    core.math = math
    core.PAPER_FEE_PCT = .6
    core.PAPER_SLIP_PCT = .1
    core._now = lambda: dt.datetime(2026,7,11,tzinfo=ZoneInfo('America/Puerto_Rico'))
    exec(compile(ast.Module(body=body,type_ignores=[]), 'main.py:pure_functions', 'exec'), core.__dict__)
    return core

def download(symbol, start, end, granularity=3600):
    rows = {}
    for a in range(start, end, 299*granularity):
        b = min(end,a+299*granularity)
        iso=lambda t: dt.datetime.fromtimestamp(t,dt.timezone.utc).isoformat().replace('+00:00','Z')
        url=f'https://api.exchange.coinbase.com/products/{symbol}/candles?granularity={granularity}&start={iso(a)}&end={iso(b)}'
        data=json.loads(subprocess.run(["curl","-fsS","--retry","2","--max-time","30",url],capture_output=True,text=True,check=True).stdout)
        if not isinstance(data,list): raise ValueError('invalid candles')
        for row in data:
            t=int(row[0])
            if start<=t<end:
                if len(row)!=6 or not all(math.isfinite(float(x)) for x in row): raise ValueError('invalid candle')
                if min(row[1:5])<=0: raise ValueError('nonpositive candle')
                if t in rows and rows[t]!=row: raise ValueError('conflicting candle')
                rows[t]=row
    expected=set(range(start,end,granularity))
    if set(rows)!=expected: raise ValueError(f'{symbol}: missing {len(expected-set(rows))} candles')
    validated = candle_index([rows[t] for t in sorted(rows)], start, end, granularity)
    return list(validated.values())

def replay(data,start,end,fee=.6,slip=.1):
    index = data_index(data, start-60*3600, end, 3600)
    core=make_core(); core.PAPER_FEE_PCT=fee; core.PAPER_SLIP_PCT=slip; plan.core=core
    core._now=lambda: dt.datetime.fromtimestamp(start,ZoneInfo('America/Puerto_Rico'))
    d=plan.new()
    for t in range(start,end,3600):
        core._now=lambda t=t: dt.datetime.fromtimestamp(t,ZoneInfo('America/Puerto_Rico'))
        markets={}
        for s in plan.PRODUCTS:
            # Only previous CLOSED candles; execute at current bar OPEN. Never use future high/low/close.
            closes=[index[s][k][4] for k in range(t-60*3600,t,3600)]
            markets[s]=core._market_from_closes(s,closes,index[s][t][3])
        plan.apply(d,markets)
    p=d['plan']
    # Terminal liquidation valuation only: do not invent extra trades or count them as wins.
    marked=plan.wealth(d)
    liquidation=d['cash']+p['allocated_cents']/100+sum(pos['qty']*d['last_prices'][s]*(1-slip/100)*(1-fee/100) for s,pos in d['positions'].items())
    # Equal-weight buy-and-hold is a context benchmark with different exposure, not a risk-matched competitor.
    hold=sum((1000/3)*(1-fee/100)/(index[s][start][3]*(1+slip/100))*index[s][end-3600][3]*(1-slip/100)*(1-fee/100) for s in plan.PRODUCTS)
    return dict(start=dt.datetime.fromtimestamp(start,dt.timezone.utc).isoformat(),end_exclusive=dt.datetime.fromtimestamp(end,dt.timezone.utc).isoformat(),fee_pct=fee,slippage_pct=slip,marked_wealth=round(marked,2),liquidation_value=round(liquidation,2),net_return_pct=round((liquidation/1000-1)*100,2),realized_net=round(d['realized'],2),fees=round(d['fees'],2),closed=p['closed'],wins=p['wins'],win_rate_pct=round(p['wins']/p['closed']*100,2) if p['closed'] else None,profit_factor=round(p['sum_wins']/p['sum_losses'],3) if p['sum_losses'] else None,max_observed_hourly_drawdown_pct=round(p['max_drawdown']*100,2),halted=p['halted'],open_positions=len(d['positions']),funds_cents=p['funds_cents'],buy_hold_liquidation=round(hold,2))

if __name__=='__main__':
    stamp=lambda s:int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())
    start,end=stamp('2026-07-11'),stamp('2026-10-10')
    cache=ROOT/'evaluation/candles_20260708_20261010.json'
    data = load_candles(cache, start-60*3600, end, 3600)
    results=[replay(data,start,end),replay(data,start,stamp('2026-08-25')),replay(data,stamp('2026-08-25'),end),replay(data,start,end,fee=1.2,slip=.2)]
    report={'source':'Coinbase Exchange public hourly candles','data_sha256':hashlib.sha256(cache.read_bytes()).hexdigest(),'engine_sha256':hashlib.sha256((ROOT/'jarvis_paper_plan.py').read_bytes()).hexdigest(),'tuned':False,'true_out_of_sample':False,'minute_execution_reproduced':False,'results':results}
    (ROOT/'evaluation/results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
