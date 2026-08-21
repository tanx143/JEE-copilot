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
    physics_slot: str = Field(description="Physics study plan with specific start and end times")
    chemistry_slot: str = Field(description="Chemistry study plan with specific start and end times")
    math_slot: str = Field(description="Math study plan with specific start and end times")
    strategy_advice: str = Field(description="Overall strategy and timetable adjustment summary")

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
st.set_page_config(page_title="JEE / WBJEE AI Copilot", layout="wide", page_icon="⚡")

# Custom Styling for Dashboard
st.markdown("""
<style>
    .stMetric {
        background-color: #1e222d;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2e364f;
    }
    .strategy-box {
        background-color: #13271f;
        border-left: 5px solid #00c853;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 25px;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ JEE / WBJEE / AUAT AI Study Copilot")

api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
selected_exam = st.sidebar.selectbox("Active Target Exam", ["JEE Main", "WBJEE", "AUAT"])

tab1, tab2, tab3, tab4 = st.tabs(["💬 Timetable Chat", "📝 PYQ Engine", "📊 Schedule Dashboard", "📈 Dynamic Progress Tracker"])
current_sched = load_schedule()

# --- TAB 1: Gemini Conversational Layout ---
with tab1:
    st.header("✨ Gemini Strategy & Schedule Copilot")
    st.caption("Ask Gemini to build, shift, or adjust your timetable. Changes save to your database in real time.")
    
    # Initialize Chat History in Session State
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Hello! I am your AI Study Assistant. Tell me your preferred study hours, tuition return time, or chapter targets, and I'll build or modify your timetable automatically."}
        ]

    # Render Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat Input Box
    if user_input := st.chat_input("e.g. I get back from tuition at 4 PM. Adjust my timetable with 1hr gym time and 3 lectures..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        if api_key:
            with st.chat_message("assistant"):
                with st.spinner("Analyzing schedule & updating database..."):
                    try:
                        new_plan = adjust_schedule_with_chat(user_input, current_sched, api_key)
                        save_schedule(new_plan.physics_slot, new_plan.chemistry_slot, new_plan.math_slot, new_plan.strategy_advice)
                        
                        response_text = f"**Schedule Updated & Synced to Database!**\n\n" \
                                        f"**Strategy Advice:** {new_plan.strategy_advice}\n\n" \
                                        f"• **Physics Slot:** {new_plan.physics_slot}\n" \
                                        f"• **Chemistry Slot:** {new_plan.chemistry_slot}\n" \
                                        f"• **Math Slot:** {new_plan.math_slot}"
                        
                        st.write(response_text)
                        st.session_state.messages.append({"role": "assistant", "content": response_text})
                    except Exception as e:
                        st.error(f"Error updating schedule: {e}")
        else:
            with st.chat_message("assistant"):
                st.error("Please enter your Gemini API Key in the left sidebar to enable AI timetable updates.")

# --- TAB 2: PYQ Engine ---
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

# --- TAB 3: Upgraded Schedule Dashboard ---
with tab3:
    st.header("📊 Active Schedule Dashboard")
    st.caption("Live, database-synced study slots generated by your AI Copilot.")
    
    # Active Strategy Card
    st.markdown(f"""
    <div class="strategy-box">
        <h4 style="margin:0; color:#00e676;">🧠 Active AI Strategy Focus</h4>
        <p style="margin-top:8px; margin-bottom:0; font-size:16px;">{current_sched['strategy']}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Subject Cards in Grid Layout
    col1, col2, col3 = st.columns(3)
    
    with col1:
        with st.container(border=True):
            st.subheader("⚡ Physics Plan")
            st.markdown(f"**Current Target & Slot:**\n\n{current_sched['physics']}")
            
    with col2:
        with st.container(border=True):
            st.subheader("🧪 Chemistry Plan")
            st.markdown(f"**Current Target & Slot:**\n\n{current_sched['chemistry']}")
            
    with col3:
        with st.container(border=True):
            st.subheader("📐 Mathematics Plan")
            st.markdown(f"**Current Target & Slot:**\n\n{current_sched['math']}")

# --- TAB 4: Progress Tracker ---
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
