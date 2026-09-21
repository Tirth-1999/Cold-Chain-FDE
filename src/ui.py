'''
Streamlit UI for the FDE Supply Chain Dispatch Console
'''

# Import necessary libraries
import os
import sys
import uuid
import json
import urllib
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from langchain_core.messages import HumanMessage, ToolMessage

# ==========================================
# 1. IMMEDIATE PATH & ENVIRONMENT RESOLUTION
# ==========================================
script_dir = Path(__file__).resolve().parent  # points to src/
project_root = script_dir.parent              # climbs to project root

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

# Import the compiled graph and tools list dynamically
from src.orchestrator import fde_agent, get_system_message

# ==========================================
# 2. SQL CREDENTIALS MAPPING FROM .ENV
# ==========================================
db_host = os.getenv("SQL_SERVER_HOST_CLOUD", "localhost")
db_port = os.getenv("SQL_SERVER_PORT", "1433")
db_user = os.getenv("SQL_VIEW_AI_AGENT_USER", "USR_FDE_RO")
db_password = os.getenv("SQL_VIEW_AI_AGENT_PASSWORD")

# Engine for the Agent to write logs using its standard credentials
connection_string = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={db_host},{db_port};"
    f"DATABASE=master;"
    f"UID={db_user};"
    f"PWD={db_password};"
    f"Encrypt=no;"
    f"TrustServerCertificate=yes;"
)

log_params = urllib.parse.quote_plus(connection_string)

log_engine = create_engine(f"mssql+pyodbc:///?odbc_connect={log_params}")

def write_audit_log(session_id, node_name, tool_name, content):
    """Silently writes agent execution traces to the SQL audit table using agent permissions."""
    try:
        with log_engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO FDE_VIEWS.AgentAuditLog (SessionID, NodeExecuted, ToolName, Content)
                VALUES (:session_id, :node_name, :tool_name, :content)
            """), {
                "session_id": session_id,
                "node_name": node_name,
                "tool_name": tool_name,
                "content": content
            })
            conn.commit()
    except Exception as e:
        print(f"Audit Log Failed (Silent): {e}")

# ==========================================
# 3. PAGE CONFIGURATION & ENTERPRISE THEME
# ==========================================
st.set_page_config(
    page_title="FDE Supply Chain Dispatch Console",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background-color: #0B0E14; color: #E2E8F0; }
    div[data-testid="stSidebar"] { background-color: #111622; border-right: 1px solid #1E293B; }
    .stMarkdown code { background-color: #1E293B !important; color: #38BDF8 !important; }
</style>
""", unsafe_allow_html=True)

QUESTION_CATALOG = {
    "🚚 Live Fleet": [
        "What are the five highest current temperature readings in the active fleet, and where are they located?",
        "Show the five active fleet records with the highest route-risk index. Include temperature, risk classification, and delay probability.",
        "How many active records are classified as High Risk and have a delay probability above 0.65?",
        "Find active fleet records near Los Angeles, around latitude 33.8 and longitude -118.1.",
        "Which active records currently have a temperature above 4°C?",
    ],
    "📘 SOP & Compliance": [
        "What temperature range must fresh perishables maintain?",
        "What should a dispatcher do immediately after a critical temperature breach?",
        "When must a vehicle be diverted to an emergency cold-storage facility?",
        "What is the difference between a Tier 1 and Tier 2 escalation?",
        "What combination of risk classification and delay probability triggers Tier 2 escalation?",
        "What should happen when port congestion near Los Angeles or Long Beach exceeds level 7?",
    ],
    "🌦️ Weather & Corridor": [
        "What are the current weather conditions at latitude 33.8 and longitude -118.1?",
        "Check the external temperature and wind speed near Los Angeles.",
        "Does the current wind-based corridor-risk indicator show normal conditions or high disruption at 33.77, -118.19?",
        "Compare current corridor conditions at 33.77, -118.19 and 34.05, -118.24. Which appears riskier?",
    ],
    "🚨 Full Investigation": [
        "Find active fleet records near Los Angeles, check the current weather there, and determine whether the temperature violates the fresh-perishables SOP. What should the dispatcher do?",
        "Find the hottest active fleet record, check conditions at its coordinates, and give me the SOP-compliant response if it is above 4°C.",
        "Identify any High Risk active records with delay probability above 0.65 and explain the required escalation.",
        "Find active records with port congestion above 7 and tell me what diversion action the SOP requires.",
        "Investigate the active record with the highest route-risk index. Include its telemetry, local weather, operational risk, and required SOP actions.",
    ],
}

# ==========================================
# 4. MULTI-USER STATE & THREAD MANAGEMENT
# ==========================================
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "ui_messages" not in st.session_state:
    st.session_state.ui_messages = []

if "system_prompt_seeded" not in st.session_state:
    st.session_state.system_prompt_seeded = False

thread_config = {"configurable": {"thread_id": st.session_state.thread_id}}

# ==========================================
# 5. SIDEBAR NAVIGATION & METADATA
# ==========================================
with st.sidebar:
    st.image(str(script_dir / "image_L25X5q.png") if (script_dir / "image_L25X5q.png").exists() else "https://cdn-icons-png.flaticon.com/512/2830/2830305.png", width=65)
    st.title("FDE Command Center")
    
    app_mode = st.radio(
        "System Mode",
        ["🧊 Dispatch Console", "💡 Questions to Try", "🛡️ Security & Audit Logs"],
        key="app_mode"
    )
    
    st.markdown("---")
    st.caption(f"Session Token: `{st.session_state.thread_id[:8]}...`")
    st.markdown(f"**Reasoning Architecture:** `{os.getenv('Agent_llm', 'DEEPSEEK')}`")
    
    st.markdown("---")
    if st.button("🗑️ Purge Dispatch Workspace Session", use_container_width=True):
        st.session_state.ui_messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.system_prompt_seeded = False
        st.rerun()

# ==========================================
# 6. VIEW ROUTING
# ==========================================

if app_mode == "🧊 Dispatch Console":
    # ------------------------------------------
    # TAB 1: CHAT UI & AGENT EXECUTION
    # ------------------------------------------
    st.title("Cold-Chain Incident Control Dashboard")
    st.caption("Production Data Engineering Pipeline • Real-Time Decision Optimization Platform")

    for entry in st.session_state.ui_messages:
        with st.chat_message(entry["role"], avatar="👤" if entry["role"] == "user" else "🤖"):
            if "traces" in entry:
                for trace in entry["traces"]:
                    if trace["type"] == "tool_input":
                        st.markdown(f"**⚡ Intent Recognized:** `{trace['name']}`")
                        with st.expander(f"📥 View Generated Input ({trace['name']})", expanded=False):
                            st.json(trace["args"])
                    elif trace["type"] == "tool_output":
                        with st.expander(f"📤 View Raw Output ({trace['name']})", expanded=False):
                            st.code(trace["content"], language="text")
            st.markdown(entry["content"])

    if user_input := st.chat_input("Query fleet telemetry, corridor updates, or compliance thresholds..."):
        
        st.session_state.ui_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="🤖"):
            final_response = ""
            current_traces = [] 
            
            with st.status("🧠 Initializing Core Reasoner Node...", expanded=True) as status:
                if not st.session_state.system_prompt_seeded:
                    turn_messages = [get_system_message(), HumanMessage(content=user_input)]
                    st.session_state.system_prompt_seeded = True
                else:
                    turn_messages = [HumanMessage(content=user_input)]

                events = fde_agent.stream(
                    {"messages": turn_messages},
                    config=thread_config,
                    stream_mode="updates"
                )
                
                for event in events:
                    for node_name, node_state in event.items():
                        
                        if node_name == "reasoner":
                            latest_msg = node_state["messages"][-1]
                            
                            # A. Intercept Tool Call Requests (Inputs)
                            if hasattr(latest_msg, "tool_calls") and latest_msg.tool_calls:
                                status.update(label="🧠 Agent generated tool parameters...")
                                for tool_call in latest_msg.tool_calls:
                                    st.markdown(f"**⚡ Intent Recognized:** `{tool_call['name']}`")
                                    with st.expander(f"📥 View Generated Input ({tool_call['name']})", expanded=False):
                                        st.json(tool_call['args'])
                                    
                                    current_traces.append({
                                        "type": "tool_input",
                                        "name": tool_call['name'],
                                        "args": tool_call['args']
                                    })
                                    
                                    write_audit_log(
                                        session_id=st.session_state.thread_id,
                                        node_name="reasoner",
                                        tool_name=tool_call['name'],
                                        content=json.dumps(tool_call['args'])
                                    )
                            
                            # B. Intercept Final Generation
                            if latest_msg.content:
                                final_response = latest_msg.content
                                status.update(label="📝 Generating Operational Resolution Report...")
                                
                                write_audit_log(
                                    session_id=st.session_state.thread_id,
                                    node_name="reasoner_final",
                                    tool_name="LLM Text Synthesis",
                                    content=final_response
                                )
                                
                        elif node_name == "tools":
                            status.update(label="🔧 Executing Enterprise Subsystem Tools...")
                            for msg in node_state.get("messages", []):
                                if isinstance(msg, ToolMessage):
                                    with st.expander(f"📤 View Raw Output ({msg.name})", expanded=False):
                                        st.code(msg.content, language="text")
                                        
                                    current_traces.append({
                                        "type": "tool_output",
                                        "name": msg.name,
                                        "content": msg.content
                                    })
                                    
                                    write_audit_log(
                                        session_id=st.session_state.thread_id,
                                        node_name="tools",
                                        tool_name=msg.name,
                                        content=msg.content
                                    )
                
                status.update(label="Incident Matrix Evaluation Complete", state="complete", expanded=False)
                
            if final_response:
                st.markdown(final_response)
                st.session_state.ui_messages.append({
                    "role": "assistant",
                    "content": final_response,
                    "traces": current_traces
                })
            else:
                error_fallback = "⚠️ Execution Timeout: System engine encountered an unresolved processing edge case."
                st.error(error_fallback)


elif app_mode == "💡 Questions to Try":
    # ------------------------------------------
    # TAB 2: GUIDED QUESTION CATALOG
    # ------------------------------------------
    st.title("💡 Questions to Try")
    st.caption("Choose a prompt below, copy it, and paste it into the Dispatch Console.")

    st.info(
        "The agent is designed for cold-chain fleet telemetry, temperature and cargo risk, "
        "weather/corridor conditions, and SOP or escalation guidance."
    )

    question_tabs = st.tabs(list(QUESTION_CATALOG.keys()))
    for question_tab, (category, questions) in zip(question_tabs, QUESTION_CATALOG.items()):
        with question_tab:
            st.markdown(f"### {category}")
            for question_number, question in enumerate(questions, start=1):
                st.markdown(f"**{question_number}. Suggested prompt**")
                st.code(question, language="text")

    st.markdown("### Useful follow-up questions")
    follow_up_col_1, follow_up_col_2 = st.columns(2)
    with follow_up_col_1:
        st.markdown(
            "- Which of those records should I prioritize first, and why?\n"
            "- What exact SOP rule supports that action?\n"
            "- Now show only the High Risk results."
        )
    with follow_up_col_2:
        st.markdown(
            "- Summarize that incident for the night-shift manager.\n"
            "- What information is still missing before the dispatcher acts?\n"
            "- Turn the result into a two-step action plan."
        )

    st.warning(
        "Out-of-scope requests such as coding help, jokes, personal advice, or unrelated topics "
        "will be refused by the agent."
    )


elif app_mode == "🛡️ Security & Audit Logs":
    # ------------------------------------------
    # TAB 3: AUDIT LOG VIEWER (REQUIRES ADMIN CREDENTIALS FROM .ENV OR INPUT)
    # ------------------------------------------
    st.title("🛡️ Enterprise Agent Audit Trail")
    st.caption("Secure database inspection of FDE_VIEWS.AgentAuditLog")
    
    st.markdown("### Database Authorization Gate")
    st.markdown("Enter high-privilege administrative credentials (defined in `.env` as `SQL_ADMIN_USER`) to query audit logs.")
    
    with st.form("admin_auth_form"):
        col1, col2 = st.columns(2)
        with col1:
            input_user = st.text_input("Admin Username", value=os.getenv("SQL_ADMIN_USER", ""))
        with col2:
            input_pass = st.text_input("Admin Password", type="password", value="")
            
        submit_admin = st.form_submit_button("Authenticate & Load Logs", use_container_width=True)

    if submit_admin:
        expected_admin_user = os.getenv("SQL_ADMIN_USER")
        expected_admin_pass = os.getenv("SQL_ADMIN_PASSWORD")
        
        if input_user == expected_admin_user and input_pass == expected_admin_pass:
            try:
                # Build an isolated admin connection string for viewing data
                admin_params = urllib.parse.quote_plus(
                    "DRIVER={ODBC Driver 18 for SQL Server};"
                    f"SERVER={db_host},{db_port};"
                    "DATABASE=master;"
                    f"UID={input_user};"
                    f"PWD={input_pass};"
                    "Encrypt=no;"
                    "TrustServerCertificate=yes;"
                )
                admin_engine = create_engine(f"mssql+pyodbc:///?odbc_connect={admin_params}")
                
                with admin_engine.connect() as conn:
                    query = """
                        SELECT LogID, Timestamp, SessionID, NodeExecuted, ToolName, Content 
                        FROM FDE_VIEWS.AgentAuditLog 
                        ORDER BY Timestamp DESC
                    """
                    df = pd.read_sql(query, conn)
                
                st.success("✅ Authenticated successfully as Admin.")
                
                if not df.empty:
                    st.dataframe(
                        df,
                        column_config={
                            "LogID": st.column_config.NumberColumn("ID", format="%d"),
                            "Timestamp": st.column_config.DatetimeColumn("Execution Time", format="DD/MM/YYYY-h:mm a"),
                            "SessionID": "Session Token",
                            "NodeExecuted": "Graph Node",
                            "ToolName": "Tool Triggered",
                            "Content": "Raw Payload Data"
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=600
                    )
                else:
                    st.info("No audit logs found in the database. Run a query in the Dispatch Console first.")
                    
            except Exception as e:
                st.error(f"Database Query Failed: {e}")
        else:
            st.error("❌ Invalid Administrator Credentials.")
