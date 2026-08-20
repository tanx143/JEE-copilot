import sqlite3
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from typing import List

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect("jee_tracker.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            chapter TEXT PRIMARY KEY,
            subject TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Structured Pydantic Schemas ---
class PYQQuestion(BaseModel):
    question: str = Field(description="The exact or highly accurate PYQ problem formulation")
    exam_year: str = Field(description="Exam tag with year, e.g., '[JEE Main 2024]', '[WBJEE 2023]'")
    options: List[str] = Field(description="List of 4 distinct options (A, B, C, D)", min_items=4, max_items=4)
    correct_option: str = Field(description="The correct option letter, e.g., 'A'")
    explanation: str = Field(description="Detailed step-by-step mathematical/conceptual solution")

class DynamicSchedule(BaseModel):
    physics_slot: str = Field(description="Updated Physics schedule and specific chapter targets")
    chemistry_slot: str = Field(description="Updated Chemistry schedule and specific chapter targets")
    math_slot: str = Field(description="Updated Math schedule and specific chapter targets")
    strategy_advice: str = Field(description="Adjusted study strategy based on user request")

# --- Agent Functions ---
def generate_pyq_quiz(subject: str, chapter: str, exam: str, api_key: str) -> PYQQuestion:
    llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", google_api_key=api_key, temperature=0.1)
    structured_llm = llm.with_structured_output(PYQQuestion)
    prompt = f"Act as an examiner. Generate a PYQ for Subject: {subject}, Chapter: {chapter}, Exam Target: {exam}."
    return structured_llm.invoke(prompt)

def adjust_schedule_with_chat(user_prompt: str, current_state: str, api_key: str) -> DynamicSchedule:
    llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", google_api_key=api_key, temperature=0.3)
    structured_llm = llm.with_structured_output(DynamicSchedule)
    prompt = f"Current Strategy: {current_state}\nUser Request: '{user_prompt}'\nRe-calculate and adjust daily study slots and chapters."
    return structured_llm.invoke(prompt)

# --- Streamlit Application UI ---
st.set_page_config(page_title="JEE / WBJEE AI Copilot", layout="wide")
st.title("🎯 JEE / WBJEE / AUAT AI Study Copilot")

api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
selected_exam = st.sidebar.selectbox("Active Target Exam", ["JEE Main", "WBJEE", "AUAT"])

if "current_schedule" not in st.session_state:
    st.session_state.current_schedule = {
        "physics": "07:00 AM - 08:00 AM: Pre-tuition formula warm-up & Electrostatics PYQs",
        "math": "10:00 AM - 01:00 PM: Integral Calculus & Differential Equations Practice",
        "chemistry": "02:30 PM - 05:00 PM: Coordination Compounds (NCERT Line-by-Line)",
        "strategy": "Schedule re-aligned around 8:00 AM - 9:30 AM Physics tuition."
    }

tab1, tab2, tab3 = st.tabs(["💬 Strategy & Timetable Chat", "📝 PYQ Practice Engine", "📊 Schedule Dashboard"])

with tab1:
    st.header("⚙️ Personalize Strategy & Schedule")
    user_customization = st.text_area("How would you like to modify your daily plan?")
    if st.button("Apply Schedule Changes"):
        if api_key:
            with st.spinner("Adjusting schedule..."):
                new_plan = adjust_schedule_with_chat(user_customization, str(st.session_state.current_schedule), api_key)
                st.session_state.current_schedule["physics"] = new_plan.physics_slot
                st.session_state.current_schedule["chemistry"] = new_plan.chemistry_slot
                st.session_state.current_schedule["math"] = new_plan.math_slot
                st.session_state.current_schedule["strategy"] = new_plan.strategy_advice
                st.success("Schedule updated! Open the Schedule Dashboard tab.")
        else:
            st.error("Please enter your Gemini API Key in the sidebar.")

with tab2:
    st.header("📝 Chapter-Wise PYQ Practice Engine")
    col_sub, col_chap = st.columns(2)
    with col_sub:
        subject = st.selectbox("Select Subject", ["Physics", "Chemistry", "Mathematics"])
    with col_chap:
        chapter = st.text_input("Target Chapter", "Calculus - Definite Integration")
        
    if st.button("Generate Chapter PYQ"):
        if api_key:
            with st.spinner("Fetching PYQ..."):
                q = generate_pyq_quiz(subject, chapter, selected_exam, api_key)
                st.session_state.active_pyq = q
        else:
            st.error("Please enter your Gemini API Key in the sidebar.")

    if "active_pyq" in st.session_state:
        q = st.session_state.active_pyq
        st.subheader(f"Tag: :blue[{q.exam_year}]")
        st.markdown(f"**Question:** {q.question}")
        user_choice = st.radio("Select Option", q.options, key="pyq_choice")
        if st.button("Submit Answer"):
            if user_choice.startswith(q.correct_option):
                st.balloons()
                st.success("Correct Answer!")
            else:
                st.error(f"Incorrect. Correct Choice: Option {q.correct_option}")
            st.info(f"**Step-by-Step Solution:**\n{q.explanation}")

# --- TAB 3: Fixed Clear UI Dashboard ---
with tab3:
    st.header("📋 Active Preparation Plan")
    st.success(f"**Current Strategy:** {st.session_state.current_schedule['strategy']}")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info(f"### ⚡ Physics Target Slot\n\n{st.session_state.current_schedule['physics']}")
    with c2:
        st.info(f"### 🧪 Chemistry Target Slot\n\n{st.session_state.current_schedule['chemistry']}")
    with c3:
        st.info(f"### 📐 Math Target Slot\n\n{st.session_state.current_schedule['math']}")
