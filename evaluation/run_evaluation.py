"""Evaluate the Meridian agent.

LOCAL checks run without NVIDIA_API_KEY: corpus, index, retrieval, SQL safety, dataset facts,
and an offline end-to-end run of the real LangGraph with a scripted stand-in for the LLM.
LIVE checks run every dataset case against the real NVIDIA model when NVIDIA_API_KEY is set.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb

import agent

DATASET = json.loads((Path(__file__).with_name("dataset.json")).read_text(encoding="utf-8"))
EXPECTED_DOCUMENTS = 15
EXPECTED_CHUNKS = 114
TOP_K = 4
LINE = "=" * 60


def normalize(text: str) -> str:
    text = str(text).lower().replace("£", "").replace("″", '"').replace("”", '"')
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    return re.sub(r"\s+", " ", text).strip()


def contains(haystack: str, needle: str) -> bool:
    return normalize(needle) in normalize(haystack)


def score(passed: int, total: int) -> str:
    percent = f"{100 * passed / total:.0f}%" if total else "n/a"
    return f"{passed:>3} / {total:<3} {percent:>5}"


def row(label: str, value: str) -> None:
    print(f"{label:<28}{value}")


def cases_and_turns() -> list[dict]:
    items = [dict(case) for case in DATASET["cases"]]
    for conversation in DATASET["conversations"]:
        for number, turn in enumerate(conversation["turns"], start=1):
            items.append({**turn, "id": f"{conversation['id']}#{number}", "category": "memory"})
    return items


# ---------------------------------------------------------------- local checks

def check_index(failures: list[str]) -> tuple[bool, int, int]:
    corpus = len(list((ROOT / "corpus").glob("*.txt")))
    collection = chromadb.PersistentClient(path=str(agent.CHROMA_DIR)).get_collection(agent.COLLECTION_NAME)
    records = collection.get(include=["metadatas", "documents"])
    complete = sum(1 for meta in records["metadatas"] if meta.get("source") and meta.get("section"))
    if corpus != EXPECTED_DOCUMENTS:
        failures.append(f"Corpus: expected {EXPECTED_DOCUMENTS} files, found {corpus}")
    if collection.count() != EXPECTED_CHUNKS:
        failures.append(f"Chunks: expected {EXPECTED_CHUNKS}, found {collection.count()}")
    if complete != collection.count():
        failures.append(f"Metadata: {collection.count() - complete} chunks lack source or section")
    return corpus == EXPECTED_DOCUMENTS, collection.count(), complete


def corpus_text(source: str) -> str:
    return (ROOT / "corpus" / source).read_text(encoding="utf-8")


def check_dataset_facts(failures: list[str]) -> tuple[int, int]:
    """Every expected fact must exist in the real database or the expected policy file."""
    passed = total = 0
    all_corpus = " ".join(corpus_text(path.name) for path in (ROOT / "corpus").glob("*.txt"))
    for item in cases_and_turns():
        evidence = ""
        if item.get("verify_sql"):
            result = agent.run_select(item["verify_sql"])
            if result.get("error"):
                total += 1
                failures.append(f"Dataset {item['id']}: verify_sql failed: {result['error']}")
                continue
            if item.get("expect_no_rows"):
                total += 1
                if result["rows"]:
                    failures.append(f"Dataset {item['id']}: expected no rows, found {result['rows']}")
                else:
                    passed += 1
            evidence += json.dumps(result["rows"], ensure_ascii=False)
        for source in item["expected_sources"]:
            if source != "meridian.db":
                evidence += " " + corpus_text(source)
        for fact in item["expected_facts"]:
            total += 1
            if contains(evidence, fact):
                passed += 1
            else:
                failures.append(f"Dataset {item['id']}: fact '{fact}' not found in its sources")
        for phrase in item.get("absent_from_corpus", []):
            total += 1
            if contains(all_corpus, phrase):
                failures.append(f"Dataset {item['id']}: '{phrase}' does appear in the corpus")
            else:
                passed += 1
    return passed, total


def check_retrieval(failures: list[str]) -> tuple[int, int, int]:
    found = top1 = total = 0
    for case in DATASET["cases"]:
        for target in case.get("retrieval", []):
            total += 1
            hits = agent.search_documents(target["query"], top_k=TOP_K)
            ranks = [
                rank
                for rank, hit in enumerate(hits, start=1)
                if hit["source"] == target["source"] and hit["section"] == target["section"]
            ]
            if ranks:
                found += 1
                top1 += ranks[0] == 1
            if not ranks or ranks[0] != 1:
                top = f"{hits[0]['source']} / {hits[0]['section']}" if hits else "none"
                rank = ranks[0] if ranks else f"not in top {TOP_K}"
                failures.append(
                    f"Retrieval '{target['query']}': expected {target['source']} / {target['section']}, "
                    f"rank {rank}, top was {top}"
                )
    return found, top1, total


def table_counts() -> dict[str, int]:
    return {
        table: agent.run_select(f"SELECT COUNT(*) AS n FROM {table}")["rows"][0]["n"]
        for table in agent.DB_TABLES
    }


def check_sql_safety(failures: list[str]) -> tuple[int, int, bool]:
    before = table_counts()
    passed = 0
    for case in DATASET["sql_safety"]:
        result = agent.run_select(case["sql"])
        error = result.get("error", "")
        if case["expect"] == "error":
            ok = bool(error) and case.get("error_contains", "") in error
            detail = error or "the query ran"
        else:
            rows = json.dumps(result.get("rows", []))
            ok = not error and case.get("contains", "") in rows
            if "max_rows" in case:
                ok = ok and len(result["rows"]) == case["max_rows"] and result["truncated"]
            detail = error or f"{len(result.get('rows', []))} rows"
        passed += ok
        if not ok:
            failures.append(f"SQL safety '{case['name']}': {detail}")
    after = table_counts()
    if before != after:
        failures.append(f"Database rows changed: {before} -> {after}")
    return passed, len(DATASET["sql_safety"]), before == after


def check_graph(failures: list[str]) -> bool:
    try:
        nodes = set(agent.build_graph().get_graph().nodes)
    except Exception as exc:
        failures.append(f"Graph does not compile: {exc}")
        return False
    expected = {"route", "retrieve_docs", "judge_docs", "retry_docs", "query_sql", "answer"}
    if not expected <= nodes:
        failures.append(f"Graph is missing nodes: {sorted(expected - nodes)}")
        return False
    return True


# ------------------------------------------------------- shared case scoring

def score_case(item: dict, result: dict) -> dict:
    answer = result.get("answer", "")
    sources = result.get("sources") or []
    supported = result.get("supported") is True
    route_ok = result.get("route") == item["expected_route"]
    facts_ok = all(contains(answer, fact) for fact in item["expected_facts"])
    if item["must_refuse"]:
        sources_ok = not sources
    else:
        sources_ok = all(any(label.startswith(source) for label in sources) for source in item["expected_sources"])
    refusal_ok = supported is not item["must_refuse"]
    return {
        "id": item["id"],
        "category": item["category"],
        "route": result.get("route"),
        "route_ok": route_ok,
        "facts_ok": facts_ok,
        "sources_ok": sources_ok,
        "refusal_ok": refusal_ok,
        "ok": route_ok and facts_ok and sources_ok and refusal_ok,
        "latency": result.get("timings", {}).get("total", 0.0),
        "detail": (
            f"route {item['expected_route']} -> {result.get('route')} | "
            f"facts {item['expected_facts']} | supported {supported} (must_refuse {item['must_refuse']})\n"
            f"      sources expected {item['expected_sources']} -> {sources}\n"
            f"      answer: {answer}"
        ),
    }


# ------------------------------------------- offline end-to-end (stubbed LLM)

# Scripted LLM replies per dataset case. The real graph, retrieval, and SQLite run unchanged;
# only agent.chat_json is replaced. "checks" are extra state assertions for the path under test.
STUB_SCRIPTS = {
    "docs_password_length": {
        "route": [{"route": "docs", "reason": "Password rules are IT security policy.", "doc_query": "minimum password length"}],
        "judge": [{"supported": True}],
        "answer": [{"supported": True, "answer": "Passwords must be at least 14 characters long.", "documents_used": [1]}],
    },
    "docs_learning_budget": {
        "route": [{"route": "docs", "reason": "The L&D budget is a policy.", "doc_query": "training money"}],
        "judge": [{"supported": False}, {"supported": True}],
        "rewrite": [{"query": "annual learning and development budget amount"}],
        "answer": [{"supported": True, "answer": "Each eligible employee has an annual L&D budget of £1,500.", "documents_used": []}],
        "checks": {"doc_retried": True},
    },
    "sql_vega_lead_location": {
        "route": [{"route": "sql", "reason": "A project lead is a database record.", "doc_query": ""}],
        "sql": [{"sql": "SELECT e.name, e.location FROM projects p JOIN employees e ON e.id = p.lead_id WHERE p.name LIKE '%Vega%'"}],
        "answer": [{"supported": True, "answer": "James Okafor leads Project Vega and is based in London."}],
        "rows_contain": ["James Okafor", "London"],
    },
    "sql_engineering_headcount": {
        "route": [{"route": "sql", "reason": "A headcount is a database aggregate.", "doc_query": ""}],
        "sql": [
            {"sql": "DELETE FROM employees"},
            {"sql": "SELECT COUNT(*) AS n FROM employees e JOIN departments d ON d.id = e.department_id WHERE d.name = 'Engineering' AND e.is_active = 1"},
        ],
        "answer": [{"supported": True, "answer": "There are 6 active employees in Engineering."}],
        "checks": {"sql_retried": True},
        "rows_contain": ["6"],
    },
    "both_aisha_equipment": {
        "route": [{"route": "both", "reason": "Needs her role from the database and the equipment policy.", "doc_query": "standard laptop for engineering roles and remote work setup allowance"}],
        "judge": [{"supported": True}],
        "sql": [{"sql": "SELECT name, role, location FROM employees WHERE name LIKE '%Aisha Patel%'"}],
        "answer": [{"supported": True, "answer": "Aisha Patel is a Software Engineer. Engineering roles receive a MacBook Pro 14\" and the remote work setup allowance is £500.", "documents_used": []}],
        "rows_contain": ["Software Engineer"],
    },
    "both_vega_hotel": {
        "route": ["not a JSON reply"],
        "judge": [{"supported": True}],
        "sql": [{"sql": "SELECT e.name FROM projects p JOIN employees e ON e.id = p.lead_id WHERE p.name LIKE '%Vega%'"}],
        "answer": [{"supported": True, "answer": "James Okafor leads Project Vega. The London hotel limit is £200 per night.", "documents_used": []}],
        "checks": {"route_reason_contains": "could not be parsed"},
    },
    "unsupported_pet_insurance": {
        "route": [{"route": "docs", "reason": "Insurance is a benefits policy question.", "doc_query": "pet insurance"}],
        "judge": [{"supported": False}, {"supported": False}],
        "rewrite": [{"query": "pet insurance employee benefit"}],
        "checks": {"doc_retried": True, "answer_is": agent.NOT_ENOUGH},
    },
    "no_match_project": {
        "route": [{"route": "sql", "reason": "A project lead is a database record.", "doc_query": ""}],
        "sql": [
            {"sql": "SELECT e.name FROM projects p JOIN employees e ON e.id = p.lead_id WHERE p.name LIKE '%Phoenix%'"},
            {"sql": "SELECT name FROM projects WHERE name LIKE '%Phoenix%'"},
        ],
        "checks": {"sql_retried": True, "answer_is": agent.NO_RECORD},
    },
    "memory_vega_location#1": {
        "route": [{"route": "sql", "reason": "A project lead is a database record.", "doc_query": ""}],
        "sql": [{"sql": "SELECT e.name FROM projects p JOIN employees e ON e.id = p.lead_id WHERE p.name LIKE '%Vega%'"}],
        "answer": [{"supported": True, "answer": "James Okafor leads Project Vega."}],
    },
    "memory_vega_location#2": {
        "route": [{"route": "sql", "reason": "The follow-up asks where the person just discussed is based.", "doc_query": ""}],
        "sql": [{"sql": "SELECT location FROM employees WHERE name LIKE '%James Okafor%'"}],
        "answer": [{"supported": True, "answer": "James Okafor is located in London."}],
        "checks": {"history_sent": "James Okafor"},
        "rows_contain": ["London"],
    },
}


def make_stub(script: dict) -> tuple:
    replies = {kind: list(items) for kind, items in script.items() if kind not in {"checks", "rows_contain"}}
    prompts: list[tuple[str, str]] = []

    def stub(system: str, user: str, max_tokens: int = 800) -> dict:
        if system == agent.ROUTER_SYSTEM:
            kind = "route"
        elif system == agent.JUDGE_SYSTEM:
            kind = "judge"
        elif system == agent.REWRITE_SYSTEM:
            kind = "rewrite"
        elif system.startswith(agent.SQL_SYSTEM):
            kind = "sql"
        elif system == agent.ANSWER_SYSTEM:
            kind = "answer"
        else:
            raise AssertionError("unknown prompt")
        prompts.append((kind, user))
        if not replies.get(kind):
            raise AssertionError(f"unexpected {kind} call")
        reply = replies[kind].pop(0)
        return agent.parse_json_object(reply if isinstance(reply, str) else json.dumps(reply))

    return stub, replies, prompts


def stub_checks(item: dict, script: dict, result: dict, replies: dict, prompts: list) -> list[str]:
    problems = [f"{kind} replies not used: {len(left)}" for kind, left in replies.items() if left]
    checks = script.get("checks", {})
    for key in ("doc_retried", "sql_retried"):
        if key in checks and bool(result.get(key)) is not checks[key]:
            problems.append(f"{key} expected {checks[key]}")
    if "answer_is" in checks and result.get("answer") != checks["answer_is"]:
        problems.append("deterministic answer not returned")
    if "route_reason_contains" in checks and checks["route_reason_contains"] not in result.get("route_reason", ""):
        problems.append("router fallback reason missing")
    if "history_sent" in checks and not any(
        "<CONVERSATION_HISTORY>" in user and checks["history_sent"] in user for kind, user in prompts if kind == "sql"
    ):
        problems.append("history was not sent to SQL generation")
    rows = json.dumps(result.get("sql_rows", []), ensure_ascii=False)
    problems += [f"rows lack '{fact}'" for fact in script.get("rows_contain", []) if not contains(rows, fact)]
    return problems


def run_offline_e2e(failures: list[str]) -> tuple[int, int]:
    items = {item["id"]: item for item in cases_and_turns()}
    real_chat = agent.chat_json
    passed = 0
    history: list[dict[str, str]] = []
    try:
        for case_id, script in STUB_SCRIPTS.items():
            item = items[case_id]
            if not case_id.endswith("#2"):
                history = []
            stub, replies, prompts = make_stub(script)
            agent.chat_json = stub
            try:
                result = agent.ask(item["question"], history)
                scored = score_case(item, result)
                problems = stub_checks(item, script, result, replies, prompts)
            except Exception as exc:
                scored, problems = {"ok": False, "detail": ""}, [f"{type(exc).__name__}: {exc}"]
                result = {}
            history.append({"question": item["question"], "answer": result.get("answer", "")})
            if scored["ok"] and not problems:
                passed += 1
            else:
                failures.append(f"Offline E2E {case_id}: {'; '.join(problems)}\n      {scored['detail']}")
    finally:
        agent.chat_json = real_chat
    return passed, len(STUB_SCRIPTS)


# ------------------------------------------------------------ live end-to-end

def run_live(failures: list[str]) -> list[dict]:
    results = []
    for case in DATASET["cases"]:
        results.append(run_live_turn(case, [], failures))
    for conversation in DATASET["conversations"]:
        history: list[dict[str, str]] = []
        for number, turn in enumerate(conversation["turns"], start=1):
            item = {**turn, "id": f"{conversation['id']}#{number}", "category": "memory"}
            scored = run_live_turn(item, history, failures)
            history.append({"question": turn["question"], "answer": scored.pop("answer", "")})
            results.append(scored)
    return results


def run_live_turn(item: dict, history: list[dict[str, str]], failures: list[str]) -> dict:
    start = time.perf_counter()
    try:
        result = agent.ask(item["question"], history)
    except Exception as exc:
        failures.append(f"Live {item['id']}: ERROR {type(exc).__name__}: {exc}")
        return {
            "id": item["id"], "category": item["category"], "route": "error", "route_ok": False,
            "facts_ok": False, "sources_ok": False, "refusal_ok": False, "ok": False,
            "latency": time.perf_counter() - start, "answer": "",
        }
    scored = score_case(item, result)
    status = "PASS" if scored["ok"] else "FAIL"
    print(f"  {status}  {item['id']:<32} {scored['route'] or '':<5} {scored['latency']:5.1f}s")
    if not scored["ok"]:
        failures.append(f"Live {item['id']}: {scored['detail']}")
    scored["answer"] = result.get("answer", "")
    return scored


def report_live(results: list[dict]) -> bool:
    def count(key: str, subset: list[dict]) -> str:
        return score(sum(r[key] for r in subset), len(subset))

    with_facts = [r for r in results if r["category"] not in {"unsupported", "no_match"}]
    refusals = [r for r in results if r["category"] in {"unsupported", "no_match"}]
    row("Routing Accuracy", count("route_ok", results))
    row("Grounded Facts", count("facts_ok", with_facts))
    row("Source Attribution", count("sources_ok", results))
    row("Unsupported Handling", count("refusal_ok", refusals))
    row("E2E Pass Rate", count("ok", results))
    latencies = [r["latency"] for r in results]
    row("Average Latency", f"{sum(latencies) / len(latencies):.1f}s")
    for route in ("docs", "sql", "both"):
        subset = [r["latency"] for r in results if r["route"] == route]
        if subset:
            row(f"  Latency ({route})", f"{sum(subset) / len(subset):.1f}s over {len(subset)}")
    return all(r["ok"] for r in results)


def main() -> None:
    failures: list[str] = []
    print(LINE)
    print("MERIDIAN AI AGENT EVALUATION")
    print(LINE)
    print("\nLOCAL DETERMINISTIC TESTS")
    corpus_ok, chunks, complete = check_index(failures)
    row("Corpus files", f"{'PASS' if corpus_ok else 'FAIL'} ({EXPECTED_DOCUMENTS})")
    row("Chunks", f"{chunks} / {EXPECTED_CHUNKS}")
    row("Metadata", f"{complete} / {chunks}")
    graph_ok = check_graph(failures)
    row("LangGraph compiles", "PASS" if graph_ok else "FAIL")
    facts_passed, facts_total = check_dataset_facts(failures)
    row("Dataset facts verified", score(facts_passed, facts_total))
    found, top1, retrieval_total = check_retrieval(failures)
    row(f"Retrieval Recall@{TOP_K}", score(found, retrieval_total))
    row("Retrieval Top-1", score(top1, retrieval_total))
    safety_passed, safety_total, unchanged = check_sql_safety(failures)
    row("SQL Safety", score(safety_passed, safety_total))
    row("Database unchanged", "PASS" if unchanged else "FAIL")

    print("\nOFFLINE/STUBBED E2E")
    e2e_passed, e2e_total = run_offline_e2e(failures)
    row("Graph paths (stubbed LLM)", score(e2e_passed, e2e_total))
    print("  The stub replaces only the LLM call; it is not evidence about the NVIDIA model.")

    local_ok = (
        corpus_ok and chunks == EXPECTED_CHUNKS and complete == chunks and graph_ok
        and facts_passed == facts_total and found == retrieval_total
        and safety_passed == safety_total and unchanged and e2e_passed == e2e_total
    )

    live_ran = bool(os.environ.get("NVIDIA_API_KEY"))
    live_ok = True
    if live_ran:
        print("\nNVIDIA NIM LIVE E2E")
        print(f"  {agent.NVIDIA_MODEL} at {agent.NVIDIA_BASE_URL}")
        live_ok = report_live(run_live(failures))
    else:
        print("\nNVIDIA NIM LIVE E2E — NOT RUN (API key unavailable)")
        print('  Set NVIDIA_API_KEY="your_key_here" to run every dataset case against the real model.')

    if failures:
        print("\nDETAILS")
        for failure in failures:
            print(f"- {failure}")
    result = "PASS" if local_ok and live_ok else "FAIL"
    if not live_ran:
        result += " (local and stubbed checks only; live E2E not run)"
    print(f"\nRESULT: {result}")
    print(LINE)
    sys.exit(0 if local_ok and live_ok else 1)


if __name__ == "__main__":
    main()
