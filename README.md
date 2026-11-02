# Organic Farm ERP

FastAPI + SQLAlchemy backend with a React/Vite dashboard for a hydroponic farm.

The React source is kept in `src/` and the production bundle is built into
`frontend/`, which is served by FastAPI. The original `code_prototype` folder
remains separate for UI comparison.

## Run

1. Create a virtual environment and install dependencies:
   `python -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and set `ENCRYPTION_KEY` to a generated Fernet key.
3. Start the API: `uvicorn app.main:app --reload`
4. Open http://127.0.0.1:8000 or http://127.0.0.1:8000/docs.

To rebuild the dashboard after frontend changes:

1. `npm install`
2. `npm run build`

The Vite development server is available with `npm run dev` on port 3000 and
proxies API requests to the FastAPI server on port 8000.

Seed credentials:
- owner / owner123
- developer / developer123

The browser stores the JWT in localStorage for this prototype only. Customer names are always encrypted in SQLite. Owners receive decrypted names; developers receive a compact customer ID instead of the encrypted value.
