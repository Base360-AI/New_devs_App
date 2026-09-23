"""Run against the local Docker assignment database; fixture writes roll back."""
import unittest
from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import requests
from fastapi import HTTPException, Response
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_pool import DatabasePool
from app.services import cache, reservations


class RevenueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = DatabasePool()
        await self.pool.initialize()
        self.connection = await self.pool.engine.connect()
        self.transaction = await self.connection.begin()
        self.session = AsyncSession(bind=self.connection)

        @asynccontextmanager
        async def get_session():
            yield self.session

        self.pool.get_session = get_session
        self.patcher = patch.object(reservations, 'db_pool', self.pool)
        self.patcher.start()
        self.tenant = 'test-' + uuid4().hex
        await self.session.execute(text('INSERT INTO tenants (id,name) VALUES (:id, :id)'), {'id': self.tenant})
        for prop, zone in [('paris', 'Europe/Paris'), ('ny', 'America/New_York')]:
            await self.session.execute(text('INSERT INTO properties (id,tenant_id,name,timezone) VALUES (:id,:tenant,:id,:zone)'),
                                       {'id': prop, 'tenant': self.tenant, 'zone': zone})

    async def asyncTearDown(self):
        self.patcher.stop()
        await self.session.close()
        await self.transaction.rollback()
        await self.connection.close()
        await self.pool.close()

    async def booking(self, prop, timestamp, amount, currency='USD'):
        await self.session.execute(text('''
            INSERT INTO reservations (id, property_id, tenant_id, check_in_date, check_out_date, total_amount, currency)
            VALUES (:id,:prop,:tenant,CAST(:date AS timestamptz),CAST(:date AS timestamptz) + INTERVAL '1 day',:amount,:currency)
        '''), {'id': uuid4().hex, 'prop': prop, 'tenant': self.tenant, 'date': datetime.fromisoformat(timestamp),
               'amount': Decimal(amount), 'currency': currency})

    async def test_paris_half_open_boundaries_and_dst(self):
        for date, amount in [('2024-02-29T22:59:59Z','100'), ('2024-02-29T23:00:00Z','1'),
                             ('2024-03-31T21:59:59Z','2'), ('2024-03-31T22:00:00Z','100')]:
            await self.booking('paris', date, amount)
        result = await reservations.calculate_monthly_revenue('paris', self.tenant)
        self.assertEqual(result['total'], '3.000')
        self.assertEqual(result['count'], 2)

    async def test_new_york_half_open_boundaries_and_dst(self):
        for date, amount in [('2024-03-01T04:59:59Z','100'), ('2024-03-01T05:00:00Z','1'),
                             ('2024-04-01T03:59:59Z','2'), ('2024-04-01T04:00:00Z','100')]:
            await self.booking('ny', date, amount)
        result = await reservations.calculate_monthly_revenue('ny', self.tenant)
        self.assertEqual(result['total'], '3.000')
        self.assertEqual(result['count'], 2)

    async def test_precision_and_currencies(self):
        for amount in ['333.333', '333.333', '333.334']:
            await self.booking('paris', '2024-03-15T12:00:00Z', amount)
        result = await reservations.calculate_monthly_revenue('paris', self.tenant)
        self.assertEqual(result['total'], '1000.000')
        await self.booking('paris', '2024-03-15T12:00:00Z', '1.005', 'EUR')
        result = await reservations.calculate_monthly_revenue('paris', self.tenant)
        self.assertIsNone(result['total'])
        self.assertEqual({r['currency']: r['total'] for r in result['totals']}, {'EUR': '1.005', 'USD': '1000.000'})

    async def test_december_rollover_and_empty_month(self):
        await self.booking('paris', '2024-12-31T22:59:59Z', '7.001')
        await self.booking('paris', '2024-12-31T23:00:00Z', '100')
        result = await reservations.calculate_monthly_revenue('paris', self.tenant, 12, 2024)
        self.assertEqual(result['total'], '7.001')
        result = await reservations.calculate_monthly_revenue('paris', self.tenant, 11, 2024)
        self.assertEqual(result['count'], 0)

    async def test_foreign_property_denied(self):
        with self.assertRaises(HTTPException) as caught:
            await reservations.calculate_monthly_revenue('paris', 'tenant-a')
        self.assertEqual(caught.exception.status_code, 404)

    async def test_seeded_property_totals(self):
        for tenant, prop, total, count in [
            ('tenant-a', 'prop-001', '2250.000', 4),
            ('tenant-a', 'prop-002', '4975.500', 4),
            ('tenant-a', 'prop-003', '6100.500', 2),
            ('tenant-b', 'prop-001', '0.000', 0),
            ('tenant-b', 'prop-004', '1776.500', 4),
            ('tenant-b', 'prop-005', '3256.000', 3),
        ]:
            result = await reservations.calculate_monthly_revenue(prop, tenant)
            self.assertEqual((result['total'], result['count']), (total, count))

    async def test_cache_isolation_and_warm_results(self):
        fake = AsyncMock()
        values = {}
        async def get(key):
            return values.get(key)
        async def put(key, ttl, value):
            values[key] = value
        fake.get.side_effect = get
        fake.setex.side_effect = put
        with patch.object(cache, 'redis_client', fake):
            for tenant, month, expected in [('tenant-a',3,'2250.000'), ('tenant-b',3,'0.000'), ('tenant-a',2,'0.000')]*2:
                result = await cache.get_revenue_summary('prop-001', tenant, month, 2024)
                self.assertEqual(result['total'], expected)
        self.assertEqual(len(values), 3)
        self.assertEqual(fake.setex.await_count, 3)

    async def test_redis_outage_falls_back_and_database_error_not_cached(self):
        fake = AsyncMock()
        fake.get.side_effect = RedisConnectionError('offline')
        fake.setex.side_effect = RedisConnectionError('offline')
        with patch.object(cache, 'redis_client', fake):
            result = await cache.get_revenue_summary('prop-001', 'tenant-a')
            self.assertEqual(result['total'], '2250.000')
            fake.setex.reset_mock()
            with patch.object(reservations, 'calculate_total_revenue', AsyncMock(side_effect=RuntimeError('offline'))):
                with self.assertRaises(RuntimeError):
                    await cache.get_revenue_summary('prop-001', 'tenant-a')
            fake.setex.assert_not_awaited()


class AccountTests(unittest.TestCase):
    def test_real_logins_and_api_isolation(self):
        base = 'http://localhost:8000/api/v1'
        accounts = [('sunset@propertyflow.com','client_a_2024','2250.000',3),
                    ('ocean@propertyflow.com','client_b_2024','0.000',3)]
        for email, password, total, count in accounts * 2:
            login = requests.post(base+'/auth/login', json={'email': email, 'password': password}, timeout=10)
            self.assertEqual(login.status_code, 200)
            headers = {'Authorization': 'Bearer '+login.json()['access_token'], 'X-Simulated-Tenant': 'tenant-a'}
            response = requests.get(base+'/dashboard/summary', params={'property_id':'prop-001'}, headers=headers, timeout=10)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['total_revenue'], total)
            self.assertIn('no-store', response.headers['Cache-Control'])
            props = requests.get(base+'/dashboard/properties', headers=headers, timeout=10)
            self.assertEqual(len(props.json()), count)
            foreign = 'prop-004' if email.startswith('sunset') else 'prop-002'
            self.assertEqual(requests.get(base+'/dashboard/summary', params={'property_id':foreign}, headers=headers, timeout=10).status_code, 404)
            self.assertEqual(requests.get(base+'/dashboard/summary', params={'property_id':'prop-001','month':13}, headers=headers, timeout=10).status_code, 422)
        self.assertEqual(requests.get(base+'/dashboard/summary',params={'property_id':'prop-001'},timeout=10).status_code, 401)


if __name__ == '__main__':
    unittest.main()

class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_identity_has_no_tenant(self):
        from app.core.tenant_resolver import TenantResolver
        self.assertIsNone(await TenantResolver.resolve_tenant_id('unknown', 'unknown@example.com'))

    async def test_missing_tenant_rejected_before_cache(self):
        from app.api.v1 import dashboard
        with patch.object(dashboard, 'get_revenue_summary', AsyncMock()) as summary:
            with self.assertRaises(HTTPException) as caught:
                await dashboard.get_dashboard_summary(Response(), 'prop-001', 3, 2024, SimpleNamespace(tenant_id=None))
            self.assertEqual(caught.exception.status_code, 403)
            summary.assert_not_awaited()

    async def test_database_failure_returns_unavailable(self):
        from app.api.v1 import dashboard
        with patch.object(dashboard, 'get_revenue_summary', AsyncMock(side_effect=RuntimeError('offline'))):
            with self.assertRaises(HTTPException) as caught:
                await dashboard.get_dashboard_summary(Response(), 'prop-001', 3, 2024, SimpleNamespace(tenant_id='tenant-a'))
            self.assertEqual(caught.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
