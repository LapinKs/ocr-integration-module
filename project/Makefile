.PHONY: build up down init

build:
	docker-compose -f docker-compose.yml build

up:
	docker-compose -f docker-compose.yml up -d

down:
	docker-compose -f docker-compose.yml down

init: build up
	python scripts/init_db.py
	python scripts/create_buckets.py
