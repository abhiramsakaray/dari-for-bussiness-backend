#!/usr/bin/env python
"""
Check what relayer configuration is actually set
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("="*80)
logger.info("POLYGON RELAYER CONFIGURATION")
logger.info("="*80)
logger.info(f"POLYGON_RELAYER_URL: {settings.POLYGON_RELAYER_URL}")
logger.info(f"POLYGON_RELAYER_API_KEY: {'(set)' if settings.POLYGON_RELAYER_API_KEY else '(not set)'}")
logger.info(f"POLYGON_RPC_URL: {settings.POLYGON_RPC_URL or '(not set)'}")
logger.info(f"POLYGON_PRIVATE_KEY: {'(set)' if getattr(settings, 'POLYGON_PRIVATE_KEY', None) else '(not set)'}")

logger.info("\n" + "="*80)
logger.info("STELLAR RELAYER CONFIGURATION")
logger.info("="*80)
logger.info(f"STELLAR_RELAYER_URL: {settings.STELLAR_RELAYER_URL}")
logger.info(f"STELLAR_RELAYER_API_KEY: {'(set)' if settings.STELLAR_RELAYER_API_KEY else '(not set)'}")
logger.info(f"STELLAR_SECRET_KEY: {'(set)' if settings.STELLAR_SECRET_KEY else '(not set)'}")

logger.info("\n" + "="*80)
logger.info("ENVIRONMENT VARIABLES")
logger.info("="*80)
polygon_env_vars = [k for k in os.environ if 'POLYGON' in k]
stellar_env_vars = [k for k in os.environ if 'STELLAR' in k]
relayer_env_vars = [k for k in os.environ if 'RELAYER' in k]

logger.info("Polygon-related:")
for var in polygon_env_vars:
    value = os.environ[var]
    if 'KEY' in var or 'SECRET' in var or 'PRIVATE' in var:
        logger.info(f"  {var}: (sensitive - {len(value)} chars)")
    else:
        logger.info(f"  {var}: {value}")

logger.info("Stellar-related:")
for var in stellar_env_vars:
    value = os.environ[var]
    if 'KEY' in var or 'SECRET' in var:
        logger.info(f"  {var}: (sensitive - {len(value)} chars)")
    else:
        logger.info(f"  {var}: {value}")

logger.info("Relayer-related:")
for var in relayer_env_vars:
    value = os.environ[var]
    if 'KEY' in var or 'SECRET' in var or 'PRIVATE' in var:
        logger.info(f"  {var}: (sensitive - {len(value)} chars)")
    else:
        logger.info(f"  {var}: {value}")

logger.info("="*80)
