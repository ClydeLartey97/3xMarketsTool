backend-install:
	cd backend && python3 -m pip install -r requirements.txt

frontend-install:
	cd frontend && npm install

backend-dev:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend-dev:
	cd frontend && npm run dev

seed:
	cd backend && python3 scripts/seed.py

test:
	cd backend && PYTHONPATH=. pytest
