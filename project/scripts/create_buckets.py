#!/usr/bin/env python3
"""
Скрипт для создания необходимых buckets в MinIO.
Запускается один раз при развёртывании.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from minio import Minio
from dotenv import load_dotenv

load_dotenv()

# Конфигурация MinIO
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
SECURE = False

# Список необходимых buckets
BUCKETS = [
    "source-images",      # Исходные изображения
    "formula-masks",      # Маски формул (npy файлы)
    "ocr-results",        # JSON результаты OCR
    "merged-trees",       # Сериализованные деревья (pickle)
    "result-pdfs",        # Сгенерированные PDF
]

def create_buckets():
    """Создаёт все необходимые buckets в MinIO"""
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
                print(f"✓ Created bucket: {bucket}")
            else:
                print(f"✓ Bucket already exists: {bucket}")

        # Настройка политик для публичного доступа (опционально)
        # for bucket in BUCKETS:
        #     policy = {
        #         "Version": "2012-10-17",
        #         "Statement": [{
        #             "Effect": "Allow",
        #             "Principal": {"AWS": ["*"]},
        #             "Action": ["s3:GetObject"],
        #             "Resource": [f"arn:aws:s3:::{bucket}/*"]
        #         }]
        #     }
        #     client.set_bucket_policy(bucket, json.dumps(policy))

        print("\nAll buckets created successfully!")

    except Exception as e:
        print(f"Error creating buckets: {e}")
        sys.exit(1)

def list_buckets():
    """Показывает все существующие buckets"""
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
