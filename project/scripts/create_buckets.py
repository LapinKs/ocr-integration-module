import os
import sys
from pathlib import Path
from minio import Minio
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
SECURE = False

BUCKETS = [
    "source-images",
    "formula-masks",
    "ocr-results",
    "merged-trees",
    "result-pdfs",
]

def create_buckets():
    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=SECURE
        )
        print(f"Connected to MinIO at {MINIO_ENDPOINT}")
        for bucket in BUCKETS:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                print(f"Created bucket: {bucket}")
            else:
                print(f"Bucket already exists: {bucket}")

        print("\nAll buckets created successfully!")
    except Exception as e:
        print(f"Error creating buckets: {e}")
        sys.exit(1)
def list_buckets():
    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=SECURE
        )

        buckets = client.list_buckets()
        print("\nExisting buckets:")
        for bucket in buckets:
            print(f"  - {bucket.name}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true', help='List existing buckets')
    args = parser.parse_args()

    if args.list:
        list_buckets()
    else:
        create_buckets()
