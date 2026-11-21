# Tensor_Titan - Ujjwal Rail Travel Assistant
### HCLTech Future Ready AI Engineer Hackathon

AI-Powered Train Travel Assistant for Bookings, Refunds, and Journey Help adhering strictly to Sections 1 to 9 of the Participant Guide.

---

## 🏗️ Architecture

* **Frontend:** Streamlit Single-Page Application (`app.py`) with internal state-based routing (`st.session_state` + `st.query_params`).
* **Backend:** FastAPI service (`backend/server.py`) exposing the 7 official hackathon REST endpoints.
* **Deterministic Domain Engine:** `backend/domain_tools.py` for exact arithmetic (refund cut-offs, fare tables, seat matrices, and idempotent Level 1 action lifecycle).
* **Teammate Integration Hook:** `backend/agent_hook.py` allows your teammates to plug their RAG and Agentic reasoning pipeline directly into the system.
* **Database:** SQLite (`data/ujjwal_rail.db`) with 100% relational integrity and provenance logs.

---

## 🚀 How to Run

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the Backend API (Port 8000)
```bash
uvicorn backend.server:app --reload --port 8000
```
API Documentation & Swagger UI available at: `http://localhost:8000/docs`

### 3. Start the Single-Page Streamlit App (Port 8501)
In a separate terminal:
```bash
streamlit run app.py
```
Open `http://localhost:8501` in your browser.

---

## 🧪 Automated Endpoint Verification
Run the complete integration test suite verifying all 7 endpoints:
```bash
python test_endpoints.py
```

---

## 🔌 Teammate Hand-off Guide (RAG & Agent Integration)

Your teammates building the **RAG** and **Agentic** modules can seamlessly plug in by defining:
```python
# In backend/teammate_agent.py
def process_with_rag_agent(passenger_id, session_id, message, as_of, trace_id):
    # Retrieve documents from RAG vector store / SQLite
    # Run LLM reasoning loop
    # Return Section 6.1 schema dictionary
    ...
```
`backend/agent_hook.py` automatically detects and delegates to this function. If absent, the built-in deterministic domain engine serves all requests.
