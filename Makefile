.PHONY: run back front pre-commit uv-install


back:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

front:
	cd frontend && npm run dev

pre-commit:
	cd backend && uv add --dev pre-commit
	uv run pre-commit install --install-hooks --overwrite

uv-install:
	cd backend && uv sync
run:
	docker compose up --build