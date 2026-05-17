# ChartDex

Voice + Codex for eCommerce metric exploration.

## Development

Install dependencies:

```sh
npm install
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
```

Run the app:

```sh
npm run dev
```

Frontend: http://localhost:5175
Backend: http://localhost:8010

Run tests:

```sh
npm test
. .venv/bin/activate && pytest backend
```
