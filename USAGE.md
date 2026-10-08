# Usage Guide

How to set up, run, and check the Meridian agent from a fresh clone.

## Prerequisites

- Python 3.14 (the version used while building this project)
- Network on first ingest, to download `sentence-transformers/all-MiniLM-L6-v2`
- A valid NVIDIA API key for live generation (routing, SQL writing, judging, answering)

## 1. Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate with `.venv\Scripts\activate`.

## 2. Prepare the database

```bash
python setup_database.py
```

This creates local `meridian.db` with departments, employees, projects, leave requests, and equipment. The script is the provided assessment asset; do not edit it.

## 3. Build the document index

```bash
python ingest.py
```

Reads every `.txt` file in `corpus/`, splits on uppercase headings, embeds locally, and writes `chroma_db/`. Expected output:

```
Indexed 15 documents, 114 chunks.
```

Safe to rerun: the same chunk IDs are upserted, so the count stays at 114.

## 4. Configure NVIDIA

```bash
export NVIDIA_API_KEY="your_key_here"
```

Do not put the key in source files or commit it. The agent calls the official hosted NIM API:

- Endpoint: `https://integrate.api.nvidia.com/v1`
- Model: `nvidia/nemotron-3.5-lightning-30b-a3b`

Without this variable, `python agent.py` exits with a short message and does not start the CLI.

## 5. Run the agent

```bash
python agent.py
```

You should see a prompt. Type a question, then `exit` to quit.

```
Ask about Meridian policies, employees, or projects. Type exit to quit.

Question: What is the minimum password length?
```

A successful turn prints `Route`, `Reason`, `Answer`, `Sources`, and `Time`. One question can also be passed as an argument:

```bash
python agent.py "Who leads Project Vega?"
```

Representative questions (answers depend on a live NVIDIA call, which was not run before submission):

| Kind | Question |
|---|---|
| Documents | What is the minimum password length? |
| Database | Who leads Project Vega and where are they located? |
| Both | What is Aisha Patel's role, what standard laptop does the hardware policy give someone in that role, and how much is the remote work setup allowance? |
| Unsupported | Does Meridian provide pet insurance? |

Follow-ups in the same CLI session use the last four turns, for example “Who leads Project Vega?” then “Where is he located?”

## 6. Run evaluation

```bash
python evaluation/run_evaluation.py
```

Three layers:

1. **Local deterministic** — corpus count, chunks, metadata, retrieval, SQL safety, database row counts, graph compile. No NVIDIA call.
2. **Offline E2E (stubbed LLM boundary)** — the real LangGraph, retrieval, and SQLite, with a scripted stand-in only for the NVIDIA chat call. Not a Nemotron run.
3. **NVIDIA hosted live E2E** — every dataset case through `ask()` against the real model.

If `NVIDIA_API_KEY` is unset, layer 3 is reported as not run and the suite still passes when layers 1 and 2 pass.

## 7. Generated local artifacts

These are created on your machine and are git-ignored:

- `meridian.db`
- `chroma_db/`
- `.venv/`

## 8. Troubleshooting

### NVIDIA_API_KEY missing

```bash
export NVIDIA_API_KEY="your_key_here"
```

Create a personal key at build.nvidia.com → Settings → API Keys.

### Database missing

```
meridian.db not found. Run python setup_database.py first.
```

Run `python setup_database.py`.

### Chroma index missing

```
chroma_db not found. Run python ingest.py first.
```

Run `python ingest.py`.

### Dependency issue

```bash
pip install -r requirements.txt
pip check
```

### NVIDIA account / API access

Live routing and answering need an account that can generate a valid personal key for the hosted NIM endpoint. Local evaluation does not.

## 9. Reset local data

From the repository root, with the virtualenv active:

```bash
rm -f meridian.db
rm -rf chroma_db
python setup_database.py
python ingest.py
```
