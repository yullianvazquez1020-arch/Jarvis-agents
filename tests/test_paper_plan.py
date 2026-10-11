"""Deterministic synthetic prices, no exchange orders, real wallets or market calls."""
import asyncio
import datetime as dt
import unittest
from unittest.mock import patch, AsyncMock
import test_jarvis as base
import jarvis_paper_plan as p

j = base.j


class PaperPlan(unittest.TestCase):
    def setUp(self):
        base.Tests.setUp(self)
        p.core = j
        self.now = dt.datetime(2026, 10, 11, 12, tzinfo=j.TZ)
        timer = patch.object(j, '_now', return_value=self.now)
        timer.start()
        self.addCleanup(timer.stop)

    def market(self, price, trend='alcista'):
        return {'price': price, 'at': j._now().isoformat(), 'trend': trend, 'rsi': 55,
                'sma20': price * .98, 'sma50': price * .96}

    def bought(self):
        d = p.new()
        p.apply(d, {'BTC-USD': self.market(100)})
        return d

    def test_no_baseline_mutation(self):
        old = j._paper_new(1234)
        j.kv_set(j.PAPER_KEY, old)
        d = self.bought()
        j.kv_set(p.KEY, d)
        self.assertEqual(j._paperload(), old)
        self.assertEqual(d['start_usd'], 1000)

    def test_risk_size_and_net_reward(self):
        d = self.bought()
        pos = d['positions']['BTC-USD']
        self.assertLessEqual(pos['risk_usd'], 20)
        self.assertLessEqual(pos['cost'], 100)
        factor = (1-j.PAPER_FEE_PCT/100)*(1-j.PAPER_SLIP_PCT/100)
        for multiple, target in ((2, 'tp1'), (3, 'tp2')):
            reward = pos['qty'] * pos[target] * factor - pos['cost']
            self.assertAlmostEqual(reward, multiple * pos['risk_usd'])

    def test_half_take_profit_once_then_full_close(self):
        d = self.bought()
        pos = dict(d['positions']['BTC-USD'])
        p.apply(d, {'BTC-USD': self.market(pos['tp1'])})
        self.assertAlmostEqual(d['positions']['BTC-USD']['qty'], pos['qty']/2)
        self.assertEqual(d['plan']['closed'], 0)
        trades = len(d['trades'])
        p.apply(d, {'BTC-USD': self.market(pos['tp1'])})
        self.assertEqual(len(d['trades']), trades)
        p.apply(d, {'BTC-USD': self.market(pos['tp2'])})
        self.assertNotIn('BTC-USD', d['positions'])
        self.assertEqual(d['plan']['closed'], 1)
        self.assertEqual(d['plan']['wins'], 1)

    def test_stop_and_gap_use_actual_price(self):
        d = self.bought()
        risk = d['positions']['BTC-USD']['risk_usd']
        p.apply(d, {'BTC-USD': self.market(50)})
        self.assertFalse(d['positions'])
        self.assertLess(d['realized'], -risk)
        self.assertEqual(d['plan']['allocated_cents'], 0)

    def test_allocation_exact_and_idempotent(self):
        d = p.new()
        d.update(cash=2000., realized=1000.)
        before = p.wealth(d)
        self.assertEqual(p.distribute(d), 100000)
        self.assertEqual(d['plan']['funds_cents'], dict(zip(p.FUNDS, [35000,15000,10000,40000])))
        self.assertEqual(d['cash'], 1000)
        self.assertEqual(p.wealth(d), before)
        self.assertEqual(p.distribute(d), 0)

    def test_losses_must_be_recovered_and_no_unrealized_distribution(self):
        d = p.new()
        d.update(cash=990., realized=-10.)
        self.assertEqual(p.distribute(d), 0)
        d.update(cash=1050., realized=50.)
        p.distribute(d)
        d.update(cash=980., realized=30.)
        self.assertEqual(p.distribute(d), 0)
        d.update(cash=1020., realized=70.)
        self.assertEqual(p.distribute(d), 2000)
        self.assertEqual(d['plan']['allocated_cents'], 7000)
        d = p.new()
        d['cash'] = 1100
        self.assertEqual(p.distribute(d), 0)

    def test_distribution_never_overdraws_or_uses_principal(self):
        d = p.new()
        d.update(cash=900., realized=100.)
        self.assertEqual(p.distribute(d), 0)
        d = p.new()
        d.update(cash=.01, realized=500.)
        d['positions']['BTC-USD'] = {'qty': 20, 'entry': 100}
        self.assertEqual(p.distribute(d), 1)
        self.assertEqual(d['cash'], 0)
        self.assertEqual(sum(d['plan']['funds_cents'].values()), 1)

    def test_daily_entry_cap_and_allowlist(self):
        d = p.new()
        markets = {s:self.market(100) for s in (*p.PRODUCTS, 'DOGE-USD', 'MATIC-USD')}
        p.apply(d, markets)
        self.assertEqual(d['plan']['spent'], 300)
        self.assertEqual(set(d['positions']), set(p.PRODUCTS))
        for symbol in list(d['positions']):
            p.sell(d, symbol, 100, d['positions'][symbol]['qty'], 'test exit')
        d['cooldown'].clear()
        p.apply(d, markets)
        self.assertFalse(d['positions'])

    def test_drawdown_circuit_is_latched(self):
        d = p.new()
        d['cash'] = 799
        p.apply(d, {'BTC-USD': self.market(100)})
        self.assertTrue(d['plan']['halted'])
        self.assertFalse(d['positions'])
        d['cash'] = 1000
        p.apply(d, {'BTC-USD': self.market(100)})
        self.assertFalse(d['positions'])

    def test_stale_price_does_not_trade_and_missing_position_blocks_entry(self):
        d = self.bought()
        old = self.market(50)
        old['at'] = (j._now()-dt.timedelta(minutes=10)).isoformat()
        p.apply(d, {'BTC-USD': old, 'ETH-USD': self.market(100)})
        self.assertEqual(set(d['positions']), {'BTC-USD'})
        self.assertIn('BTC-USD', d['plan']['missing_prices'])

    def test_weekly_rebalance_does_not_force_new_entries(self):
        d = self.bought()
        # Synthetic oversize position, with profit targets far away, exercises weekly trim.
        pos = d['positions']['BTC-USD']
        pos.update(qty=5., initial_qty=5., cost=500., tp1=1000., tp2=2000.)
        d['cash'] = 500.
        d['plan']['last_rebalance'] = (j._now()-dt.timedelta(days=8)).isoformat()
        p.apply(d, {'BTC-USD': self.market(100, 'lateral')})
        self.assertLess(d['positions']['BTC-USD']['qty'], 5.)
        self.assertIn('rebalance', d['trades'][-1]['reason'])

    def test_private_command_and_snapshot(self):
        tasks=j._Tasks()
        asyncio.run(j._tg_route({'text':'/plantrading','chat':{'id':123,'type':'group'},'from':{'id':123}},tasks))
        self.assertIn('privado', tasks.items[0][1][1])
        self.assertEqual(j.RESTORE_KEYS['paper_plan'], p.KEY)

    def test_missing_prices_prevent_distribution(self):
        d = p.new()
        d.update(cash=1100., realized=100.)
        d['plan']['missing_prices'] = ['BTC-USD']
        self.assertEqual(p.distribute(d), 0)

    def test_accounting_invariant_across_generated_paths(self):
        import random
        rng = random.Random(21)
        d = p.new()
        for step in range(120):
            with patch.object(j, '_now', return_value=self.now+dt.timedelta(hours=step)):
                markets = {s:self.market(rng.uniform(70,150)) for s in p.PRODUCTS}
                p.apply(d, markets)
                unrealized = sum(pos['qty']*d['last_prices'][s]-pos['cost'] for s,pos in d['positions'].items())
                self.assertAlmostEqual(p.wealth(d), 1000+d['realized']+unrealized, places=5)
                self.assertGreaterEqual(d['cash'], -1e-7)
                self.assertEqual(sum(d['plan']['funds_cents'].values()), d['plan']['allocated_cents'])
                self.assertLessEqual(d['plan']['spent'], 300)
