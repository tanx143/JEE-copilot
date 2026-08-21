import os
import streamlit as st
import google.generativeai as genai
from groq import Groq
from pydantic import BaseModel, Field
from supabase import create_client, Client
from typing import List, Optional
import PIL.Image
import json
from streamlit_mic_recorder import speech_to_text

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

# --- AI Routing Logic ---
def adjust_schedule_with_chat(user_prompt: str, current_state: dict, api_key: str, provider: str, image=None) -> DynamicSchedule:
    prompt = f"Current Schedule State: {current_state}\nUser Request: '{user_prompt}'\nGenerate updated structured timetable."

    if provider == "Google Gemini":
        genai.configure(api_key=api_key)
        # Using gemini-1.5-flash-latest fixes the 404 error
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        
        contents = [prompt]
        if image:
            contents.append(image)
            
        response = model.generate_content(
            contents,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=DynamicSchedule,
                temperature=0.3
            )
        )
        return DynamicSchedule.model_validate_json(response.text)

    elif provider == "Groq (Llama 3)":
        client = Groq(api_key=api_key)
        json_schema = DynamicSchedule.model_json_schema()
        
        system_msg = f"You are a study schedule assistant. You MUST respond ONLY with valid JSON matching this schema:\n{json.dumps(json_schema)}"
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        return DynamicSchedule.model_validate_json(completion.choices[0].message.content)

def generate_pyq_quiz(subject: str, chapter: str, exam: str, api_key: str, provider: str) -> PYQQuestion:
    prompt = f"Subject: {subject}, Chapter: {chapter}, Exam Target: {exam}. Generate a realistic PYQ with step-by-step answer key."

    if provider == "Google Gemini":
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=PYQQuestion,
                temperature=0.1
            )
        )
        return PYQQuestion.model_validate_json(response.text)

    elif provider == "Groq (Llama 3)":
        client = Groq(api_key=api_key)
        json_schema = PYQQuestion.model_json_schema()
        system_msg = f"You are an exam generator. Respond ONLY in valid JSON matching this schema:\n{json.dumps(json_schema)}"
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return PYQQuestion.model_validate_json(completion.choices[0].message.content)

# --- UI Setup ---
st.set_page_config(page_title="JEE / WBJEE AI Copilot", layout="wide", page_icon="⚡")

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
    .gemini-card {
        background-color: #1a1d24;
        border: 1px solid #2d323e;
        border-radius: 12px;
        padding: 20px;
        margin-top: 15px;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ JEE / WBJEE / AUAT AI Study Copilot")

# --- Sidebar Configuration ---
ai_provider = st.sidebar.selectbox("Choose AI Engine", ["Google Gemini", "Groq (Llama 3)"], key="ai_provider_select")

if ai_provider == "Google Gemini":
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password", key="sidebar_gemini_key")
    st.sidebar.caption("Get key from [aistudio.google.com](https://aistudio.google.com/)")
else:
    api_key = st.sidebar.text_input("Enter Groq API Key", type="password", key="sidebar_groq_key")
    st.sidebar.caption("Get 100% free key from [console.groq.com](https://console.groq.com)")

selected_exam = st.sidebar.selectbox("Active Target Exam", ["JEE Main", "WBJEE", "AUAT"], key="sidebar_target_exam")

tab1, tab2, tab3, tab4 = st.tabs(["💬 Timetable Chat", "📝 PYQ Engine", "📊 Schedule Dashboard", "📈 Dynamic Progress Tracker"])
current_sched = load_schedule()

# --- TAB 1: Chat Interface ---
with tab1:
    st.header(f"✨ Timetable Copilot ({ai_provider})")
    st.caption("Prompt your AI assistant via text, speech recorder, or image attachment.")

    if "voice_text" not in st.session_state:
        st.session_state.voice_text = ""

    if "latest_response" in st.session_state:
        st.markdown(f"""
        <div class="gemini-card">
            <h4 style="color: #4da6ff; margin-top:0;">✨ Active Generated Plan</h4>
            <p>{st.session_state.latest_response}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("**🎙️ Record Your Speech:** Click to start speaking")
    recorded_text = speech_to_text(
        language='en',
        start_prompt="🎙️ Start Voice Recording",
        stop_prompt="🔴 Stop & Transcribe",
        just_once=True,
        key="STT"
    )

    if recorded_text and recorded_text != st.session_state.voice_text:
        st.session_state.voice_text = recorded_text
        st.rerun()

    with st.container(border=True):
        c_add, c_input, c_send = st.columns([0.6, 8.1, 0.7])
        
        with c_add:
            with st.popover("➕", help="Attach Image Routine (Gemini Only)"):
                uploaded_file = st.file_uploader("Upload Routine File", type=["png", "jpg", "jpeg"], key="routine_file_uploader")
            if "uploaded_file" not in locals():
                uploaded_file = None

        with c_input:
            user_text = st.text_input(
                "chat_bar_input",
                value=st.session_state.voice_text,
                placeholder="Ask AI to build or modify your daily timetable...",
                label_visibility="collapsed",
                key="main_chat_bar_input"
            )

        with c_send:
            submit_btn = st.button("⬆️", use_container_width=True, key="main_chat_submit_btn")

    if submit_btn and (user_text or uploaded_file):
        if api_key:
            with st.spinner(f"Updating schedule via {ai_provider}..."):
                try:
                    img = PIL.Image.open(uploaded_file) if uploaded_file else None
                    
                    if uploaded_file and ai_provider == "Groq (Llama 3)":
                        st.warning("Note: Image processing is currently only supported on Google Gemini. Proceeding with text prompt.")

                    new_plan = adjust_schedule_with_chat(user_text, current_sched, api_key, ai_provider, image=img)
                    save_schedule(new_plan.physics_slot, new_plan.chemistry_slot, new_plan.math_slot, new_plan.strategy_advice)
                    
                    summary = f"**Strategy:** {new_plan.strategy_advice}\n\n" \
                              f"• **Physics:** {new_plan.physics_slot}\n" \
                              f"• **Chemistry:** {new_plan.chemistry_slot}\n" \
                              f"• **Math:** {new_plan.math_slot}"
                    
                    st.session_state.latest_response = summary
                    st.session_state.voice_text = ""
                    st.success("Database updated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error executing plan: {e}")
        else:
            st.error(f"Please enter your {ai_provider} API Key in the sidebar.")

# --- TAB 2: PYQ Engine ---
with tab2:
    st.header("📝 Chapter-Wise PYQ Practice Engine")
    c_sub, c_chap = st.columns(2)
    with c_sub: subject = st.selectbox("Select Subject", ["Physics", "Chemistry", "Mathematics"], key="pyq_subject_select")
    with c_chap: chapter = st.text_input("Target Chapter", "Calculus - Definite Integration", key="pyq_chapter_input")
    if st.button("Generate Chapter PYQ", key="generate_pyq_btn"):
        if api_key:
            with st.spinner(f"Fetching PYQ using {ai_provider}..."):
                st.session_state.active_pyq = generate_pyq_quiz(subject, chapter, selected_exam, api_key, ai_provider)
        else: st.error("Please enter API Key.")

    if "active_pyq" in st.session_state:
        q = st.session_state.active_pyq
        st.subheader(f"Tag: :blue[{q.exam_year}]")
        st.markdown(f"**Question:** {q.question}")
        user_choice = st.radio("Select Option", q.options, key="pyq_choice")
        if st.button("Submit Answer", key="submit_pyq_ans_btn"):
            if user_choice.startswith(q.correct_option): st.balloons(); st.success("Correct!")
            else: st.error(f"Incorrect. Correct Option: {q.correct_option}")
            st.info(f"**Solution:**\n{q.explanation}")

# --- TAB 3: Schedule Dashboard ---
with tab3:
    st.header("📊 Active Schedule Dashboard")
    st.caption("Live, database-synced study slots generated by your AI Copilot.")
    
    st.markdown(f"""
    <div class="strategy-box">
        <h4 style="margin:0; color:#00e676;">🧠 Active AI Strategy Focus</h4>
        <p style="margin-top:8px; margin-bottom:0; font-size:16px;">{current_sched['strategy']}</p>
    </div>
    """, unsafe_allow_html=True)
    
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

# --- TAB 4: Dynamic Progress Tracker ---
with tab4:
    st.header("📈 Interactive Chapter & Lecture Tracker")
    
    with st.expander("➕ Add New Chapter Target", expanded=True):
        c_day, c_sub, c_chap, c_lecs = st.columns([1, 1, 2, 1])
        with c_day: day_in = st.number_input("Day #", min_value=1, value=1, step=1, key="tracker_day_input")
        with c_sub: sub_in = st.selectbox("Subject", ["Physics", "Chemistry", "Mathematics"], key="tracker_sub_input")
        with c_chap: chap_in = st.text_input("Chapter Name", placeholder="e.g. Fluid Mechanics", key="tracker_chap_input")
        with c_lecs: lecs_in = st.number_input("Total Lectures", min_value=1, value=4, step=1, key="tracker_lecs_input")
        
        if st.button("Add Chapter Target", key="add_chap_target_btn"):
            if chap_in:
                add_chapter_target(day_in, sub_in, chap_in, lecs_in)
                st.success(f"Added Day {day_in}: {chap_in} ({lecs_in} lectures)!")
                st.rerun()
            else:
                st.warning("Please enter a chapter name.")

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

                st.write("**Mark Finished Lectures:**")
                cols = st.columns(min(ch['total_lectures'], 8))
                new_completed = 0
                
                for i in range(1, ch['total_lectures'] + 1):
                    col_idx = (i - 1) % 8
                    is_checked = i <= ch['completed_lectures']
                    
                    if cols[col_idx].checkbox(f"L{i}", value=is_checked, key=f"ch_{ch['id']}_l{i}"):
                        new_completed += 1
                
                if new_completed != ch['completed_lectures']:
                    update_lecture_progress(ch['id'], new_completed)
                    st.rerun()

                ch_pct = new_completed / ch['total_lectures']
                st.progress(ch_pct)
                st.caption(f"Chapter Progress: **{new_completed}/{ch['total_lectures']} Lectures** ({ch_pct * 100:.0f}% Completed)")
    else:
        st.info("No chapter targets set yet. Add a chapter above to start tracking!")
