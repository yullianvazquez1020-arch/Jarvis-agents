"""Isolated spot-only paper experiment. No exchange orders, wallets or real transfers."""
import asyncio
import datetime as dt
import math
import os

KEY = 'jarvis:paper_plan_v1'
PRODUCTS = ('BTC-USD', 'ETH-USD', 'SOL-USD')
FUNDS = ('tax_reserve', 'operations', 'subscriptions', 'personal')
core = None


def enabled():
    return os.getenv('PAPER_PLAN_ENABLED', 'false').lower() in ('true', '1', 'yes')


def new():
    d = core._paper_new(1000)
    d['plan'] = {'funds_cents': dict.fromkeys(FUNDS, 0), 'allocated_cents': 0,
                 'peak': 1000., 'max_drawdown': 0., 'halted': False, 'closed': 0,
                 'wins': 0, 'sum_wins': 0., 'sum_losses': 0., 'last_rebalance': None,
                 'day': '', 'spent': 0., 'last_distribution': None}
    return d


def load():
    d = core.kv_get(KEY, None)
    return d if isinstance(d, dict) and 'plan' in d else new()


def trading_equity(d):
    return d['cash'] + sum(p['qty'] * d['last_prices'].get(symbol, p['entry'])
                           for symbol, p in d['positions'].items())


def wealth(d):
    return trading_equity(d) + d['plan']['allocated_cents'] / 100


def levels(price, budget):
    """Risk includes entry/exit fees and modeled slippage; targets are NET 2R and 3R."""
    fee, slip = core.PAPER_FEE_PCT / 100, core.PAPER_SLIP_PCT / 100
    entry = price * (1 + slip)
    qty = budget * (1 - fee) / entry
    stop = entry * .95
    net_at_stop = qty * stop * (1 - slip) * (1 - fee)
    risk = budget - net_at_stop
    divisor = qty * (1 - slip) * (1 - fee)
    return {'stop': stop, 'tp1': (budget + 2 * risk) / divisor,
            'tp2': (budget + 3 * risk) / divisor, 'risk_usd': risk}


def distribute(d):
    """Allocate only recovered, realized profit backed by cash and total marked profit.

    Repeated calls are idempotent. Losing trades must recover prior realized losses and
    the previously allocated hurdle. Funds remain part of wealth, outside trading cash.
    """
    plan = d['plan']
    if plan.get('missing_prices'):
        return 0
    ceiling = min(d['realized'], wealth(d) - d['start_usd'])
    target = max(0, math.floor((ceiling + 1e-9) * 100))
    cents = min(max(0, target - plan['allocated_cents']), max(0, math.floor(d['cash'] * 100)))
    if cents <= 0:
        return 0
    total = plan['allocated_cents'] + cents
    shares = [total * pct // 100 for pct in (35, 15, 10)]
    shares.append(total - sum(shares))
    plan['funds_cents'] = dict(zip(FUNDS, shares))
    plan['allocated_cents'] = total
    d['cash'] = round(d['cash'] - cents / 100, 8)
    plan['last_distribution'] = {'at': core._now().isoformat(), 'cents': cents}
    return cents


def sell(d, symbol, price, qty, reason):
    pos = d['positions'][symbol]
    qty = min(qty, pos['qty'])
    cost = pos['cost'] * qty / pos['qty']
    fill = price * (1 - core.PAPER_SLIP_PCT / 100)
    gross = qty * fill
    fee = gross * core.PAPER_FEE_PCT / 100
    net, pnl = gross - fee, gross - fee - cost
    d['cash'] = round(d['cash'] + net, 8)
    d['fees'] = round(d['fees'] + fee, 8)
    d['realized'] = round(d['realized'] + pnl, 8)
    pos['cycle_pnl'] += pnl
    closed = qty >= pos['qty'] - 1e-12
    t = core._paper_trade(d, product=symbol, side='sell', qty=qty, price=fill, usd=net,
                         fee=fee, pnl=pnl, reason=reason, position_closed=closed)
    if closed:
        cycle = pos['cycle_pnl']
        t['cycle_pnl'] = cycle
        plan = d['plan']
        plan['closed'] += 1
        plan['wins'] += int(cycle > 0)
        plan['sum_wins'] += max(0, cycle)
        plan['sum_losses'] += max(0, -cycle)
        del d['positions'][symbol]
        d['cooldown'][symbol] = (core._now() + dt.timedelta(hours=6)).isoformat()
    else:
        pos['qty'] -= qty
        pos['cost'] -= cost
    distribute(d)
    return t


def apply(d, markets):
    now = core._now()
    plan, events = d['plan'], []
    valid = {}
    for symbol, m in markets.items():
        if symbol not in PRODUCTS:
            continue
        try:
            price = float(m['price'])
            timestamp = dt.datetime.fromisoformat(m['at'])
            if not math.isfinite(price) or price <= 0 or not -60 <= (now - timestamp).total_seconds() <= 120:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        valid[symbol] = m
        d['last_prices'][symbol] = price
        d['last_market'][symbol] = m
    missing = set(d['positions']) - set(valid)
    plan['missing_prices'] = sorted(missing)
    total = wealth(d)
    plan['peak'] = max(plan['peak'], total)
    dd = max(0, 1 - total / plan['peak'])
    plan['max_drawdown'] = max(plan['max_drawdown'], dd)
    if dd >= .20:
        plan['halted'] = True
    if plan['day'] != now.date().isoformat():
        plan.update(day=now.date().isoformat(), spent=0.)
    last = plan['last_rebalance']
    rebalance = last is None or now - dt.datetime.fromisoformat(last) >= dt.timedelta(days=7)
    for symbol, m in valid.items():
        price = float(m['price'])
        pos = d['positions'].get(symbol)
        if not pos:
            continue
        if plan['halted'] or price <= pos['stop']:
            reason = 'corte por caída del 20%' if plan['halted'] else 'stop simulado'
            events.append(sell(d, symbol, price, pos['qty'], reason))
            continue
        if not pos['tp1_done'] and price >= pos['tp1']:
            pos['tp1_done'] = True
            events.append(sell(d, symbol, price, min(pos['initial_qty'] / 2, pos['qty']), 'TP1: 50% a 2R neto'))
        pos = d['positions'].get(symbol)
        if pos and price >= pos['tp2']:
            events.append(sell(d, symbol, price, pos['qty'], 'TP2: resto a 3R neto'))
        elif pos and rebalance:
            excess = pos['qty'] * price - max(0, trading_equity(d)) * .25
            if excess >= 10:
                events.append(sell(d, symbol, price, excess / price, 'rebalance semanal: reducir concentración al 25%'))
    if rebalance and not missing:
        plan['last_rebalance'] = now.isoformat()
    # Exits precede entries. If any price is missing, never size fresh risk on stale equity.
    for symbol, m in valid.items():
        if wealth(d) <= plan['peak'] * .8:
            plan['halted'] = True
        if plan['halted'] or missing or symbol in d['positions']:
            continue
        cd = d['cooldown'].get(symbol)
        if cd and dt.datetime.fromisoformat(cd) > now:
            continue
        rsi = m.get('rsi')
        if m.get('trend') != 'alcista' or not isinstance(rsi, (int, float)) or not 45 <= rsi <= 70:
            continue
        price = float(m['price'])
        risk_fraction = levels(price, 1)['risk_usd']
        budget = min(d['cash'], max(0, trading_equity(d)) * .02 / risk_fraction,
                     100., max(0, 300. - plan['spent']))
        budget = math.floor((budget + 1e-9) * 100) / 100
        if budget < 10:
            continue
        event = core._paper_buy(d, symbol, price, budget, 'plan simulado: tendencia y riesgo máximo 2%')
        pos = d['positions'][symbol]
        pos.update(levels(price, budget), initial_qty=pos['qty'], tp1_done=False, cycle_pnl=0.)
        plan['spent'] = round(plan['spent'] + budget, 8)
        events.append(event)
    total = wealth(d)
    plan['peak'] = max(plan['peak'], total)
    plan['max_drawdown'] = max(plan['max_drawdown'], max(0, 1 - total / plan['peak']))
    if plan['max_drawdown'] >= .20:
        plan['halted'] = True
    d['equity'] = (d['equity'] + [{'at': now.isoformat(timespec='minutes'), 'v': round(total, 2)}])[-2200:]
    d['last_run'] = now.isoformat(timespec='minutes')
    return events


def status():
    d = load()
    p = d['plan']
    closed = p['closed']
    wins = p['wins']
    losses = closed - wins
    avg_win = p['sum_wins'] / wins if wins else None
    avg_loss = p['sum_losses'] / losses if losses else None
    profit_factor = p['sum_wins'] / p['sum_losses'] if p['sum_losses'] > 0 else None
    win_rate = wins / closed if closed else None
    expectancy = None
    if win_rate is not None and avg_win is not None and avg_loss is not None:
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    total = wealth(d)
    peak = p.get('peak', 1000.)
    current_dd = max(0, 1 - total / peak) if peak > 0 else 0
    max_dd = p['max_drawdown']
    recovery = None
    if max_dd > 0 and d['realized'] > 0:
        recovery = d['realized'] / (max_dd * peak)
    # Simple risk-of-ruin approximation (fixed fraction, assumes average RR).
    ror = None
    if win_rate is not None and avg_win is not None and avg_loss is not None and avg_loss > 0:
        rr = avg_win / avg_loss
        edge = (win_rate * (rr + 1) - 1) / rr if rr > 0 else -1
        if edge > 0 and win_rate < 1:
            ror = ((1 - edge) / (1 + edge)) ** (100 / 2)  # rough for 2% risk units
        elif edge <= 0:
            ror = 1.0
    # Equity curve volatility (std of recent changes).
    eq = d.get('equity') or []
    vol = None
    if len(eq) >= 10:
        vals = [x['v'] for x in eq[-100:] if isinstance(x.get('v'), (int, float))]
        if len(vals) >= 5:
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            vol = math.sqrt(var) / mean if mean else None
    return {'simulated': True, 'enabled': enabled(), 'wealth': round(total, 2),
            'trading_cash': round(d['cash'], 2), 'realized_net': round(d['realized'], 2),
            'funds': {k: v / 100 for k, v in p['funds_cents'].items()},
            'closed_positions': closed, 'win_rate': 100 * win_rate if win_rate is not None else None,
            'avg_win': round(avg_win, 2) if avg_win is not None else None,
            'avg_loss': round(avg_loss, 2) if avg_loss is not None else None,
            'profit_factor': round(profit_factor, 2) if profit_factor is not None else None,
            'expectancy': round(expectancy, 2) if expectancy is not None else None,
            'max_drawdown_pct': round(max_dd * 100, 2),
            'current_drawdown_pct': round(current_dd * 100, 2),
            'recovery_factor': round(recovery, 2) if recovery is not None else None,
            'risk_of_ruin_approx': round(ror, 3) if ror is not None else None,
            'equity_vol_pct': round(vol * 100, 2) if vol is not None else None,
            'halted': p['halted'],
            'positions': d['positions'], 'last_run': d['last_run'], 'real_transfers': False,
            'sample_sufficient': closed >= 30}


def text():
    s = status()
    win = f"{s['win_rate']:.1f}%" if s['win_rate'] is not None else 'sin muestra'
    avg_w = f"${s['avg_win']:.2f}" if s['avg_win'] is not None else '—'
    avg_l = f"${s['avg_loss']:.2f}" if s['avg_loss'] is not None else '—'
    pf = f"{s['profit_factor']:.2f}" if s['profit_factor'] is not None else '—'
    exp = f"${s['expectancy']:.2f}" if s['expectancy'] is not None else '—'
    cdd = f"{s['current_drawdown_pct']:.1f}%"
    mdd = f"{s['max_drawdown_pct']:.1f}%"
    rec = f"{s['recovery_factor']:.2f}" if s['recovery_factor'] is not None else '—'
    ror = f"{s['risk_of_ruin_approx']:.1%}" if s['risk_of_ruin_approx'] is not None else '—'
    vol = f"{s['equity_vol_pct']:.1f}%" if s['equity_vol_pct'] is not None else '—'
    sample = 'muestra suficiente (≥30)' if s['sample_sufficient'] else 'muestra insuficiente (<30 cierres)'
    return (f"🧪 Plan nuevo · SIMULADO · separado del historial anterior\n"
            f"Estado: {'activo' if s['enabled'] else 'apagado'} · capital inicial $1,000\n"
            f"Patrimonio ${s['wealth']:.2f} · efectivo para operar ${s['trading_cash']:.2f}\n"
            f"P&L realizado neto ${s['realized_net']:.2f}\n"
            f"Fondos simulados: impuestos ${s['funds']['tax_reserve']:.2f}; operación ${s['funds']['operations']:.2f}; "
            f"suscripciones ${s['funds']['subscriptions']:.2f}; personal ${s['funds']['personal']:.2f}\n"
            f"Cierres {s['closed_positions']} · aciertos {win} (meta >55%) · {sample}\n"
            f"Ganancia media {avg_w} · pérdida media {avg_l} · profit factor {pf} · expectancy {exp}\n"
            f"Riesgo: DD actual {cdd} · DD máx {mdd} · recovery {rec} · RoR aprox. {ror} · vol equity {vol}\n"
            f"Pausa por riesgo: {s['halted']}\n"
            f"Riesgo previsto ≤2% por entrada; objetivos netos 2R/3R. Los saltos de precio pueden superar el stop.\n"
            f"Reserva 35/15/10/40: solo ganancias realizadas recuperadas, nunca transferencias reales. "
            f"35% es provisional para CPA, no una tasa fiscal. Última revisión: {s['last_run'] or 'pendiente'}. "
            f"No habilita dinero real.")


async def tick(now):
    if not enabled() or not await asyncio.to_thread(core._claim, 'jarvis:paperplan:' + now.strftime('%Y%m%d%H%M'), 300):
        return
    results = await asyncio.gather(*(core.paper_market(p) for p in PRODUCTS), return_exceptions=True)
    markets = {p: r for p, r in zip(PRODUCTS, results) if isinstance(r, dict)}
    if not markets:
        raise ValueError('No fresh public prices')
    def save_step():
        with core._data_lock:
            d = load()
            before = d['plan']['allocated_cents']
            events = apply(d, markets)
            core.kv_set(KEY, d)
            return bool(events), d['plan']['allocated_cents'] > before
    traded, allocated = await asyncio.to_thread(save_step)
    if (traded or allocated) and core.TG_TOKEN and core.TG_OWNER:
        await core._tg_send(core.TG_OWNER, text())


def install(j):
    global core
    core = j
    original_tick, original_route = j._tick_v38, j._tg_route
    async def wrapped_tick(now, can_send):
        await original_tick(now, can_send)
        try:
            await tick(now)
        except Exception as exc:
            j._sched_state['last_error'] = 'paper_plan: ' + type(exc).__name__
    async def route(msg, background):
        command = str(msg.get('text', '')).strip().lower().split('@')[0]
        if command != '/plantrading':
            return await original_route(msg, background)
        chat = str(msg.get('chat', {}).get('id', ''))
        answer = await asyncio.to_thread(text) if j.is_owner_private(msg) else 'Usa tu chat privado para el plan de práctica.'
        background.add_task(j._tg_safe_send, chat, answer)
        return {'ok': True}
    j._tick_v38, j._tg_route = wrapped_tick, route
    j.HELP_TEXT += '\n/plantrading — experimento separado de $1,000, riesgo y reparto SIMULADOS'
    j.RESTORE_KEYS['paper_plan'] = KEY
    original_snapshot = j.snapshot
    def snapshot():
        with j._data_lock:
            return {**original_snapshot(), 'paper_plan': load()}
    j.snapshot = snapshot
