# Cold-Chain FDE

Agentic cold-chain logistics console for an FDE-style demo: legacy MSSQL telemetry, SOP retrieval over Pinecone, RBAC-hardened SQL views, and a Streamlit dispatch UI powered by LangGraph.

## What this repo does

| Phase | Goal |
|-------|------|
| **0** | Ingest legacy fleet CSV into SQL Server (`TBL_SC_FLEET_HIST_RAW`) |
| **1** | Embed and upsert the cold-chain incident SOP into Pinecone |
| **2** | Create read-only agent views + RBAC (`USR_FDE_RO`) |
| **3** | LangGraph tools + orchestrator (telemetry, weather, SOP search) |
| **4** | Agent audit log table (`FDE_VIEWS.AgentAuditLog`) |
| **5** | Streamlit dispatch console |
| **6** | EC2 deployment (systemd + ODBC Driver 18) |

Step-by-step runbooks live in [`docs/Instruction.md`](docs/Instruction.md).

## Project layout

```text
data/
  raw/          # source logistics CSV
  policy/       # SOP markdown
  source/       # dataset download pointer
scripts/
  Ingesting_legacy_data.py
  ingesting_pinecode_data.py
  Setup_security_and_view.sql
src/
  agent_tools.py
  orchestrator.py
  ui.py
  trail.sql
  prompts/system_prompt.txt
```

## Prerequisites

- Python 3.12+
- Docker (for SQL Server 2022) **or** an EC2 host with ≥ 2 GB RAM
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- API keys / secrets in a local `.env` (never commit this file):
  - SQL Server host, port, admin + read-only agent credentials
  - `OPENAI_API_KEY` (or your configured LLM keys)
  - `PINECONE_API_KEY` (+ index name as used by the scripts)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # if present; otherwise create .env from Instruction.md
```

### Legacy SQL (Phase 0)

```bash
docker run -v mssql_data:/var/opt/mssql \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=<your-sa-password>" \
  -p 1433:1433 \
  --name legacy-mssql \
  -d mcr.microsoft.com/mssql/server:2022-latest

python scripts/Ingesting_legacy_data.py
```

### SOP vectors (Phase 1)

```bash
python scripts/ingesting_pinecode_data.py
```

### Security views (Phase 2)

Run `scripts/Setup_security_and_view.sql` against SQL Server as `sa`, then connect as `USR_FDE_RO`.

### Agent + UI (Phases 3–5)

```bash
# optional smoke checks
python src/agent_tools.py
python src/orchestrator.py

# dispatch console
streamlit run src/ui.py
```

## Notes

- SQL Server 2022 containers need **at least 2 GB RAM**; smaller EC2 types will exit with a memory error.
- The agent should query `FDE_VIEWS.VW_ACTIVE_FLEET`, not the raw legacy table.
- Full deployment (systemd, `msodbcsql18`) is documented under Phase 6 in `docs/Instruction.md`.
