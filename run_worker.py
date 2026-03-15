#!/usr/bin/env python3
from __future__ import annotations

from backend.app.worker import celery_app


if __name__ == "__main__":
    celery_app.worker_main(["worker", "--loglevel=info", "-Q", "pdf_jobs"])
