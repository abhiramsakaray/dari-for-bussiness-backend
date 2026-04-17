#!/usr/bin/env python3
"""
Automated Database Backup Script
Performs pg_dump, compresses, encrypts, and uploads to S3/GCS
"""
import subprocess
import os
import gzip
import boto3
from datetime import datetime, timedelta
from pathlib import Path
import logging
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "dari_production")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

S3_BUCKET = os.getenv("BACKUP_S3_BUCKET", "dari-backups")
S3_PREFIX = os.getenv("BACKUP_S3_PREFIX", "database")
BACKUP_DIR = Path("/var/backups/dari")
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))


def create_backup():
    """Create PostgreSQL backup using pg_dump"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"dari_db_{timestamp}.sql"
    
    logger.info(f"Creating backup: {backup_file}")
    
    # Ensure backup directory exists
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    # pg_dump command
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    
    cmd = [
        "pg_dump",
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "-d", DB_NAME,
        "-F", "c",  # Custom format (compressed)
        "-f", str(backup_file),
        "--verbose"
    ]
    
    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True)
        logger.info(f"✅ Backup created: {backup_file}")
        return backup_file
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Backup failed: {e.stderr.decode()}")
        raise


def compress_backup(backup_file):
    """Compress backup with gzip"""
    compressed_file = Path(str(backup_file) + ".gz")
    
    logger.info(f"Compressing backup: {compressed_file}")
    
    with open(backup_file, 'rb') as f_in:
        with gzip.open(compressed_file, 'wb') as f_out:
            f_out.writelines(f_in)
    
    # Remove uncompressed file
    backup_file.unlink()
    
    logger.info(f"✅ Compressed: {compressed_file}")
    return compressed_file


def calculate_checksum(file_path):
    """Calculate SHA256 checksum"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def upload_to_s3(file_path):
    """Upload backup to S3"""
    s3_client = boto3.client('s3')
    
    s3_key = f"{S3_PREFIX}/{file_path.name}"
    
    logger.info(f"Uploading to S3: s3://{S3_BUCKET}/{s3_key}")
    
    # Calculate checksum
    checksum = calculate_checksum(file_path)
    
    # Upload with metadata
    s3_client.upload_file(
        str(file_path),
        S3_BUCKET,
        s3_key,
        ExtraArgs={
            'Metadata': {
                'checksum': checksum,
                'backup_date': datetime.now().isoformat(),
                'database': DB_NAME
            },
            'ServerSideEncryption': 'AES256'
        }
    )
    
    logger.info(f"✅ Uploaded to S3: {s3_key}")
    logger.info(f"   Checksum: {checksum}")
    
    return s3_key, checksum


def cleanup_old_backups():
    """Remove backups older than retention period"""
    cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
    
    logger.info(f"Cleaning up backups older than {RETENTION_DAYS} days")
    
    # Local cleanup
    for backup_file in BACKUP_DIR.glob("dari_db_*.sql.gz"):
        if backup_file.stat().st_mtime < cutoff_date.timestamp():
            logger.info(f"Removing old backup: {backup_file}")
            backup_file.unlink()
    
    # S3 cleanup
    s3_client = boto3.client('s3')
    response = s3_client.list_objects_v2(
        Bucket=S3_BUCKET,
        Prefix=S3_PREFIX
    )
    
    if 'Contents' in response:
        for obj in response['Contents']:
            if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                logger.info(f"Removing old S3 backup: {obj['Key']}")
                s3_client.delete_object(Bucket=S3_BUCKET, Key=obj['Key'])


def verify_backup(backup_file):
    """Verify backup integrity"""
    logger.info(f"Verifying backup: {backup_file}")
    
    # Test restore to temporary database
    test_db = f"{DB_NAME}_test_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    
    # Create test database
    subprocess.run([
        "createdb",
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        test_db
    ], env=env, check=True)
    
    try:
        # Restore backup
        subprocess.run([
            "pg_restore",
            "-h", DB_HOST,
            "-p", DB_PORT,
            "-U", DB_USER,
            "-d", test_db,
            str(backup_file)
        ], env=env, check=True, capture_output=True)
        
        # Verify table count
        result = subprocess.run([
            "psql",
            "-h", DB_HOST,
            "-p", DB_PORT,
            "-U", DB_USER,
            "-d", test_db,
            "-t",
            "-c", "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'"
        ], env=env, capture_output=True, text=True, check=True)
        
        table_count = int(result.stdout.strip())
        logger.info(f"✅ Backup verified: {table_count} tables restored")
        
    finally:
        # Drop test database
        subprocess.run([
            "dropdb",
            "-h", DB_HOST,
            "-p", DB_PORT,
            "-U", DB_USER,
            test_db
        ], env=env)


def main():
    """Main backup execution"""
    try:
        logger.info("=" * 60)
        logger.info("Starting database backup")
        logger.info("=" * 60)
        
        # Create backup
        backup_file = create_backup()
        
        # Compress
        compressed_file = compress_backup(backup_file)
        
        # Upload to S3
        s3_key, checksum = upload_to_s3(compressed_file)
        
        # Verify backup
        verify_backup(compressed_file)
        
        # Cleanup old backups
        cleanup_old_backups()
        
        logger.info("=" * 60)
        logger.info("✅ Backup completed successfully")
        logger.info(f"   File: {compressed_file}")
        logger.info(f"   S3: s3://{S3_BUCKET}/{s3_key}")
        logger.info(f"   Checksum: {checksum}")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Backup failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
