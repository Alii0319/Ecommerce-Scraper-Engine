# Baseline State Report

- Date: 2026-07-21
- Commit SHA: `4583a0b2b29fce35a676be902fd963b701a3949b`
- Branch: `fix/production-readiness`

## Baseline Measurements

- **Backend `manage.py check`**: Passed with 0 issues identified.
- **Backend `manage.py test`**: 12 tests passed, 0 failures.
- **Docker Compose Status**: `db` and `redis` services healthy.
- **Known Issues**:
  1. `TrackedProduct.objects.select_for_update()` called outside `transaction.atomic()` in `backend/trackers/tasks.py`.
  2. Potential duplicate WebSocket alerts for unchanged price states below threshold.
  3. Non-standardized WebSocket message payloads between backend and frontend.
  4. Django served via Gunicorn/WSGI instead of Daphne/ASGI in `Dockerfile`.
  5. Missing SSRF validation on target URLs.
  6. Redis connection check blocking Django startup.
