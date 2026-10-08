# Demo

A live NVIDIA NIM transcript of five or more questions was not recorded. NVIDIA account verification blocked creation of an API key, so hosted generation has not been run.

Local checks that do not call NVIDIA were executed. See `python evaluation/run_evaluation.py`: corpus, retrieval, SQL safety, graph compilation, and a stubbed LangGraph walkthrough. Stubbed results are not NVIDIA model output.

To produce the required live demo after a key is available:

```bash
export NVIDIA_API_KEY="your_key_here"
python agent.py
```

Ask at least five questions covering policy documents and the database, for example:

1. What is the minimum password length?
2. How much is the annual learning and development budget?
3. Who leads Project Vega and where are they located?
4. What is Aisha Patel's role, and what standard laptop does the hardware policy give someone in that role?
5. Does Meridian provide pet insurance?
