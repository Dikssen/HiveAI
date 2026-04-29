"""
Sample backend error scenario for analysis.
Describes a production incident that can be analyzed by BackendDeveloperAgent / DevOpsAgent.
"""

INCIDENT_DESCRIPTION = """
Production Incident — 2024-01-15 10:00 UTC
===========================================

Symptoms:
- POST /api/orders returning 503 for all users
- GET /api/products returning 503
- Error: "QueuePool limit of size 5 overflow 10 reached, connection timed out"

Timeline:
- 09:30 — Celery task queue depth reached 842 (normal: <50)
- 09:30 — 4 Celery workers OOM-killed (memory: 7.8GB / 8GB)
- 09:45 — Load increased 60% from daily reporting cron job
- 10:00 — DB connection pool exhausted (pool_size=5, max_overflow=10)
- 10:00 — All API endpoints returning 503
- 10:01 — On-call engineer increased pool_size to 20
- 10:01 — Service started recovering

Root cause hypothesis:
1. Daily report cron job at 09:45 triggered N+1 queries
2. Each report query opened DB connections but didn't release them properly
3. Memory pressure caused workers to be OOM-killed
4. Dead workers held DB connections that were never returned to pool
5. Pool exhausted → 503 for all users

Impact:
- ~45 minutes of degraded service
- ~2,100 failed requests
- 3 customer complaints (T-1003, T-1009, T-1013)

Action items:
- [ ] Fix N+1 query in report generation (add eager loading)
- [ ] Add index on orders.created_at
- [ ] Increase DB pool_size to 20 permanently
- [ ] Add memory limits to Celery workers
- [ ] Add circuit breaker for report generation
- [ ] Add alerting when pool utilization > 70%
"""
