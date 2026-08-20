import os
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from supabase import create_client, Client
from typing import List

# --- Supabase Cloud Database Connection ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

def load_schedule():
    response = supabase.table("schedule").select("*").eq("id", 1).execute()
    if response.data:
        return response.data[0]
    return {
        "physics": "Not set",
        "chemistry": "Not set",
        "math": "Not set",
        "strategy": "Not set"
    }

def save_schedule(physics: str, chemistry: str, math: str, strategy: str):
    supabase.table("schedule").upsert({
        "id": 1,
        "physics": physics,
        "chemistry": chemistry,
        "math": math,
        "strategy": strategy
    }).execute()

# --- Pydantic Schemas ---
class DynamicSchedule(BaseModel):
    physics_slot: str = Field(description="Updated Physics schedule and specific chapter targets")
    chemistry_slot: str = Field(description="Updated Chemistry schedule and specific chapter targets")
    math_slot: str = Field(description="Updated Math schedule and specific chapter targets")
    strategy_advice: str = Field(description="Adjusted study strategy based on user request")

class PYQQuestion(BaseModel):
    question: str = Field(description="The exact or highly accurate PYQ problem formulation")
    exam_year: str = Field(description="Exam tag with year, e.g., '[JEE Main 2024]'")
    options: List[str] = Field(description="4 distinct options (A, B, C, D)", min_items=4, max_items=4)
    correct_option: str = Field(description="The correct option letter, e.g., 'A'")
    explanation: str = Field(description="Step-by-step solution derivation")

# --- Agent Functions ---
def adjust_schedule_with_chat(user_prompt: str, current_state: dict, api_key: str) -> DynamicSchedule:
    llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", google_api_key=api_key, temperature=0.3)
    structured_llm = llm.with_structured_output(DynamicSchedule)
    prompt = f"Current Strategy: {current_state}\nUser Request: '{user_prompt}'\nRe-calculate and adjust daily study slots and chapters."
    return structured_llm.invoke(prompt)

def generate_pyq_quiz(subject: str, chapter: str, exam: str, api_key: str) -> PYQQuestion:
    llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", google_api_key=api_key, temperature=0.1)
    structured_llm = llm.with_structured_output(PYQQuestion)
    prompt = f"Act as an examiner. Generate a PYQ for Subject: {subject}, Chapter: {chapter}, Exam Target: {exam}."
    return structured_llm.invoke(prompt)

# --- Streamlit UI ---
st.set_page_config(page_title="JEE / WBJEE AI Copilot", layout="wide")
st.title("🎯 JEE / WBJEE / AUAT AI Study Copilot")

api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
selected_exam = st.sidebar.selectbox("Active Target Exam", ["JEE Main", "WBJEE", "AUAT"])

tab1, tab2, tab3 = st.tabs(["💬 Strategy & Timetable Chat", "📝 PYQ Practice Engine", "📊 Schedule Dashboard"])

# Load current schedule from Cloud DB
current_sched = load_schedule()

with tab1:
    st.header("⚙️ Personalize Strategy & Schedule")
    user_customization = st.text_area("How would you like to modify your daily plan?")
    if st.button("Apply Schedule Changes"):
        if api_key:
            with st.spinner("Syncing with Cloud DB..."):
                new_plan = adjust_schedule_with_chat(user_customization, current_sched, api_key)
                save_schedule(
                    new_plan.physics_slot,
                    new_plan.chemistry_slot,
                    new_plan.math_slot,
                    new_plan.strategy_advice
                )
                st.success("Schedule updated and synced across all devices!")
                st.rerun()
        else:
            st.error("Please enter your Gemini API Key in the sidebar.")

with tab2:
    st.header("📝 Chapter-Wise PYQ Practice Engine")
    c_sub, c_chap = st.columns(2)
    with c_sub:
        subject = st.selectbox("Select Subject", ["Physics", "Chemistry", "Mathematics"])
    with c_chap:
        chapter = st.text_input("Target Chapter", "Calculus - Definite Integration")
        
    if st.button("Generate Chapter PYQ"):
        if api_key:
            with st.spinner("Fetching PYQ..."):
                st.session_state.active_pyq = generate_pyq_quiz(subject, chapter, selected_exam, api_key)
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

with tab3:
    st.header("📋 Active Preparation Plan (Cloud Synced)")
    st.success(f"**Current Strategy:** {current_sched['strategy']}")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"### ⚡ Physics Target Slot\n\n{current_sched['physics']}")
    with col2:
        st.info(f"### 🧪 Chemistry Target Slot\n\n{current_sched['chemistry']}")
    with col3:
        st.info(f"### 📐 Math Target Slot\n\n{current_sched['math']}")
