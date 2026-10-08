# Meridian assistant

Uses the official NVIDIA NIM API: model `nvidia/nemotron-3.5-lightning-30b-a3b` at `https://integrate.api.nvidia.com/v1`.

A valid `NVIDIA_API_KEY` is required for live LLM execution. Local deterministic evaluation can run without it.

Tested with Python 3.14.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python setup_database.py
python ingest.py
export NVIDIA_API_KEY="your_key_here"
python agent.py
python evaluation/run_evaluation.py
```

Create the key at build.nvidia.com → Settings → API Keys → Generate Personal Key.

The first ingestion downloads `sentence-transformers/all-MiniLM-L6-v2`; after that it runs locally.

Type `exit` to quit the CLI. A single question can also be passed directly:

```bash
python agent.py "Who leads Project Vega?"
```
