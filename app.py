import os
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from supabase import create_client, Client
from typing import List

# --- Supabase Connection ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- DB Helper Functions ---
def load_schedule():
    res = supabase.table("schedule").select("*").eq("id", 1).execute()
    return res.data[0] if res.data else {"physics": "Not set", "chemistry": "Not set", "math": "Not set", "strategy": "Not set"}

def save_schedule(physics: str, chemistry: str, math: str, strategy: str):
    supabase.table("schedule").upsert({"id": 1, "physics": physics, "chemistry": chemistry, "math": math, "strategy": strategy}).execute()

def add_chapter_target(day_num: int, subject: str, chapter: str, total_lecs: int):
    supabase.table("chapter_lectures").insert({
        "day_number": day_num,
        "subject": subject,
        "chapter_name": chapter,
        "total_lectures": total_lecs,
        "completed_lectures": 0
    }).execute()

def update_lecture_progress(chapter_id: int, completed_count: int):
    supabase.table("chapter_lectures").update({"completed_lectures": completed_count}).eq("id", chapter_id).execute()

def get_all_chapters():
    res = supabase.table("chapter_lectures").select("*").order("day_number", desc=False).execute()
    return res.data if res.data else []

def delete_chapter(chapter_id: int):
    supabase.table("chapter_lectures").delete().eq("id", chapter_id).execute()

# --- Pydantic Schemas ---
class DynamicSchedule(BaseModel):
    physics_slot: str = Field(description="Physics study plan with specific timings")
    chemistry_slot: str = Field(description="Chemistry study plan with specific timings")
    math_slot: str = Field(description="Math study plan with specific timings")
    strategy_advice: str = Field(description="Overall strategy modification")

class PYQQuestion(BaseModel):
    question: str = Field(description="PYQ formulation")
    exam_year: str = Field(description="Exam tag with year")
    options: List[str] = Field(description="4 distinct options", min_items=4, max_items=4)
    correct_option: str = Field(description="Correct option letter")
    explanation: str = Field(description="Step-by-step solution")

# --- AI Agents ---
def adjust_schedule_with_chat(user_prompt: str, current_state: dict, api_key: str) -> DynamicSchedule:
    llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", google_api_key=api_key, temperature=0.3)
    return llm.with_structured_output(DynamicSchedule).invoke(f"Current Strategy: {current_state}\nUser Request: '{user_prompt}'")

def generate_pyq_quiz(subject: str, chapter: str, exam: str, api_key: str) -> PYQQuestion:
    llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", google_api_key=api_key, temperature=0.1)
    return llm.with_structured_output(PYQQuestion).invoke(f"Subject: {subject}, Chapter: {chapter}, Exam: {exam}")

# --- UI Setup ---
st.set_page_config(page_title="JEE / WBJEE AI Copilot", layout="wide")
st.title("🎯 JEE / WBJEE / AUAT AI Study Copilot")

api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
selected_exam = st.sidebar.selectbox("Active Target Exam", ["JEE Main", "WBJEE", "AUAT"])

tab1, tab2, tab3, tab4 = st.tabs(["💬 Timetable Chat", "📝 PYQ Engine", "📊 Schedule Dashboard", "📈 Dynamic Progress Tracker"])
current_sched = load_schedule()

with tab1:
    st.header("⚙️ Personalize Strategy & Schedule")
    user_customization = st.text_area("How would you like to modify your daily plan?")
    if st.button("Apply Schedule Changes"):
        if api_key:
            with st.spinner("Syncing with Cloud DB..."):
                new_plan = adjust_schedule_with_chat(user_customization, current_sched, api_key)
                save_schedule(new_plan.physics_slot, new_plan.chemistry_slot, new_plan.math_slot, new_plan.strategy_advice)
                st.success("Schedule updated!")
                st.rerun()
        else:
            st.error("Please enter your Gemini API Key.")

with tab2:
    st.header("📝 Chapter-Wise PYQ Practice Engine")
    c_sub, c_chap = st.columns(2)
    with c_sub: subject = st.selectbox("Select Subject", ["Physics", "Chemistry", "Mathematics"])
    with c_chap: chapter = st.text_input("Target Chapter", "Calculus - Definite Integration")
    if st.button("Generate Chapter PYQ"):
        if api_key:
            with st.spinner("Fetching PYQ..."):
                st.session_state.active_pyq = generate_pyq_quiz(subject, chapter, selected_exam, api_key)
        else: st.error("Please enter API Key.")

    if "active_pyq" in st.session_state:
        q = st.session_state.active_pyq
        st.subheader(f"Tag: :blue[{q.exam_year}]")
        st.markdown(f"**Question:** {q.question}")
        user_choice = st.radio("Select Option", q.options, key="pyq_choice")
        if st.button("Submit Answer"):
            if user_choice.startswith(q.correct_option): st.balloons(); st.success("Correct!")
            else: st.error(f"Incorrect. Correct Option: {q.correct_option}")
            st.info(f"**Solution:**\n{q.explanation}")

with tab3:
    st.header("📋 Active Preparation Plan")
    st.success(f"**Current Strategy:** {current_sched['strategy']}")
    col1, col2, col3 = st.columns(3)
    with col1: st.info(f"### ⚡ Physics Target Slot\n\n{current_sched['physics']}")
    with col2: st.info(f"### 🧪 Chemistry Target Slot\n\n{current_sched['chemistry']}")
    with col3: st.info(f"### 📐 Math Target Slot\n\n{current_sched['math']}")

with tab4:
    st.header("📈 Interactive Chapter & Lecture Tracker")
    
    # 1. Input Form
    with st.expander("➕ Add New Chapter Target", expanded=True):
        c_day, c_sub, c_chap, c_lecs = st.columns([1, 1, 2, 1])
        with c_day: day_in = st.number_input("Day #", min_value=1, value=1, step=1)
        with c_sub: sub_in = st.selectbox("Subject", ["Physics", "Chemistry", "Mathematics"])
        with c_chap: chap_in = st.text_input("Chapter Name", placeholder="e.g. Fluid Mechanics")
        with c_lecs: lecs_in = st.number_input("Total Lectures", min_value=1, value=4, step=1)
        
        if st.button("Add Chapter Target"):
            if chap_in:
                add_chapter_target(day_in, sub_in, chap_in, lecs_in)
                st.success(f"Added Day {day_in}: {chap_in} ({lecs_in} lectures)!")
                st.rerun()
            else:
                st.warning("Please enter a chapter name.")

    # 2. Render Interactive Chapter Cards & Progress Bars
    chapters = get_all_chapters()
    if chapters:
        total_syllabus_lecs = sum(c['total_lectures'] for c in chapters)
        total_completed_lecs = sum(c['completed_lectures'] for c in chapters)
        overall_pct = (total_completed_lecs / total_syllabus_lecs) if total_syllabus_lecs > 0 else 0.0

        st.markdown("---")
        st.subheader("📊 Overall Preparation Progress")
        col_m1, col_m2 = st.columns(2)
        with col_m1: st.metric("Total Lectures Finished", f"{total_completed_lecs} / {total_syllabus_lecs}")
        with col_m2: st.metric("Overall Completion Rate", f"{overall_pct * 100:.1f}%")
        st.progress(overall_pct)

        st.markdown("---")
        st.subheader("📚 Active Chapters Tracker (Sorted by Day)")

        for ch in chapters:
            with st.container(border=True):
                head_col, del_col = st.columns([5, 1])
                with head_col:
                    st.markdown(f"### 📅 **Day {ch.get('day_number', 1)}** | {ch['subject']}: **{ch['chapter_name']}**")
                with del_col:
                    if st.button("🗑️ Delete", key=f"del_{ch['id']}"):
                        delete_chapter(ch['id'])
                        st.rerun()

                # Interactive Checkbox Grid
                st.write("**Mark Finished Lectures:**")
                cols = st.columns(min(ch['total_lectures'], 8))
                new_completed = 0
                
                for i in range(1, ch['total_lectures'] + 1):
                    col_idx = (i - 1) % 8
                    is_checked = i <= ch['completed_lectures']
                    
                    if cols[col_idx].checkbox(f"L{i}", value=is_checked, key=f"ch_{ch['id']}_l{i}"):
                        new_completed += 1
                
                # Update DB if checkbox state changed
                if new_completed != ch['completed_lectures']:
                    update_lecture_progress(ch['id'], new_completed)
                    st.rerun()

                # Individual Chapter Level Progress Bar
                ch_pct = new_completed / ch['total_lectures']
                st.progress(ch_pct)
                st.caption(f"Chapter Progress: **{new_completed}/{ch['total_lectures']} Lectures** ({ch_pct * 100:.0f}% Completed)")
    else:
        st.info("No chapter targets set yet. Add a chapter above to start tracking!")
