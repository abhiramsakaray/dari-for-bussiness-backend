#!/usr/bin/env python3
"""Clean up recovery metadata from completed Polygon refunds"""

import os
import sys
sys.path.insert(0, '.')
os.environ['ENV'] = 'dev'

from app.core.database import SessionLocal
from app.models.models import Refund

db = SessionLocal()

try:
    refunds = db.query(Refund).filter(
        Refund.id.in_(['ref_7S27vsN9r7tWMB8D', 'ref_qvgt2tak4tOwCm7i'])
    ).all()
    
    for refund in refunds:
        old_failure_reason = refund.failure_reason
        refund.failure_reason = None  # Clear recovery notes since refund succeeded
        
        print(f"✅ Cleaned {refund.id}")
        print(f"   Old: {old_failure_reason}")
        print(f"   New: {refund.failure_reason}")
    
    db.commit()
    print(f"\n✅ Updated {len(refunds)} refunds")
    
finally:
    db.close()
