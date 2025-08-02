import streamlit as st
import openai
import pandas as pd
import time
import os
import uuid
import streamlit_authenticator as stauth

# --- CONFIGURATION ---
openai.api_key = 'YOUR_OPENAI_KEY'

ADMIN_USERS = {
    "admin@fetch.com": {"name": "Admin User", "password": "admin123"},
}
REVIEWER_USERS = {
    "reviewer1@fetch.com": {"name": "Reviewer One", "password": "review123"},
    "reviewer2@fetch.com": {"name": "Reviewer Two", "password": "review123"},
}

QUEUE_TYPES = ['Licensed', 'Nonlicensed']
PRIORITY_LEVELS = ['High', 'Medium', 'Low']

# -- In-memory storage for projects and results --
if "projects" not in st.session_state:
    st.session_state.projects = []  # Each: dict with info, queue, status, etc.
if "current_review" not in st.session_state:
    st.session_state.current_review = None

# -- Auth System (Demo fallback) --
def authenticate_user(email, password):
    if email in ADMIN_USERS and ADMIN_USERS[email]["password"] == password:
        return "admin"
    elif email in REVIEWER_USERS and REVIEWER_USERS[email]["password"] == password:
        return "reviewer"
    else:
        return None

# -- Login UI --
def login_page():
    st.title("Fetch Data Cleanliness Portal - Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type='password')
    if st.button("Login"):
        user_type = authenticate_user(email, password)
        if user_type:
            st.session_state.user_email = email
            st.session_state.user_type = user_type
            st.session_state.user_name = (ADMIN_USERS.get(email) or REVIEWER_USERS.get(email))["name"]
            st.success(f"Welcome {st.session_state.user_name}!")
            st.stop()
        else:
            st.error("Invalid credentials")

# --- ADMIN FUNCTIONS ---
def admin_dashboard():
    st.header("Admin Dashboard")
    st.write(f"Hello, {st.session_state.user_name} (Admin)")

    # --- Upload new project ---
    st.subheader("Upload New Data Pull")
    with st.form("upload_form"):
        project_name = st.text_input("Project Name")
        queue_type = st.selectbox("Queue", QUEUE_TYPES)
        priority = st.selectbox("Priority", PRIORITY_LEVELS)
        notes = st.text_area("Notes")
        file = st.file_uploader("CSV File", type="csv")
        submit = st.form_submit_button("Upload & Queue")
        if submit and file and project_name:
            project_id = str(uuid.uuid4())
            file_path = f"project_{project_id}.csv"
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())
            st.session_state.projects.append({
                "id": project_id,
                "project_name": project_name,
                "queue": queue_type,
                "priority": priority,
                "notes": notes,
                "filename": file_path,
                "status": "Waiting",
                "reviewer": None,
                "stats": {"fidocount": 0, "brand_edits": 0, "cat_edits": 0, "desc_edits": 0, "avg_time": 0, "done": 0},
                "review_data": [],
                "start_time": None,
                "completed_time": None
            })
            st.success("Project uploaded and queued!")

    # --- List/Manage Projects ---
    st.subheader("Project Queue")
    projects = st.session_state.projects
    if not projects:
        st.info("No projects uploaded yet.")
    else:
        queue_df = pd.DataFrame([{
            "Project": p["project_name"],
            "Queue": p["queue"],
            "Priority": p["priority"],
            "Status": p["status"],
            "Reviewer": p["reviewer"] if p["reviewer"] else "-",
            "FIDOs": p["stats"]["fidocount"],
            "Done": p["stats"]["done"]
        } for p in projects])
        st.dataframe(queue_df)

    # --- Dashboard Analytics ---
    st.subheader("Review Analytics")
    # Basic stats
    total_edits = sum(p["stats"]["brand_edits"] + p["stats"]["cat_edits"] + p["stats"]["desc_edits"] for p in projects)
    avg_time = round(sum(p["stats"]["avg_time"] for p in projects if p["stats"]["done"] > 0)/max(sum(p["stats"]["done"] for p in projects), 1), 2)
    st.metric("Total Edits (All Projects)", total_edits)
    st.metric("Average Review Time (sec)", avg_time)

    # Download buttons for completed projects
    for p in projects:
        if p["status"] == "Done" and p["review_data"]:
            csv = pd.DataFrame(p["review_data"]).to_csv(index=False)
            st.download_button(f"Download Cleaned CSV ({p['project_name']})", csv, f"{p['project_name']}_cleaned.csv")

# --- REVIEWER FUNCTIONS ---
def reviewer_dashboard():
    st.header(f"Welcome, {st.session_state.user_name} (Reviewer)")
    # Choose queue
    queue_choice = st.selectbox("Choose Queue", QUEUE_TYPES)
    # List projects in queue, sorted by priority
    queue_projects = [p for p in st.session_state.projects if p["queue"] == queue_choice and p["status"] == "Waiting"]
    queue_projects.sort(key=lambda x: PRIORITY_LEVELS.index(x["priority"]))
    if not queue_projects:
        st.info("No projects available in this queue.")
        return
    proj_names = [f"[{p['priority']}] {p['project_name']}" for p in queue_projects]
    proj_idx = st.selectbox("Available Projects", list(range(len(proj_names))), format_func=lambda x: proj_names[x])
    selected_project = queue_projects[proj_idx]

    if st.button("Start Review", key=selected_project["id"]):
        # Assign to reviewer, set status
        for p in st.session_state.projects:
            if p["id"] == selected_project["id"]:
                p["status"] = "In Progress"
                p["reviewer"] = st.session_state.user_email
                p["start_time"] = time.time()
                break
        st.session_state.current_review = selected_project["id"]
        st.experimental_rerun()

    # If user is already reviewing a project
    if st.session_state.current_review:
        do_review(st.session_state.current_review)

# --- REVIEW PROCESS ---
def do_review(project_id):
    project = next((p for p in st.session_state.projects if p["id"] == project_id), None)
    if not project:
        st.error("Project not found.")
        return
    st.subheader(f"Reviewing: {project['project_name']} ({project['queue']}, {project['priority']})")
    df = pd.read_csv(project["filename"])
    total = len(df)
    if project["stats"]["fidocount"] == 0:
        project["stats"]["fidocount"] = total

    idx = len(project["review_data"])
    if idx >= total:
        # Review finished
        project["status"] = "Done"
        project["completed_time"] = time.time()
        project["stats"]["done"] = total
        st.success("Review complete!")
        st.stop()

    row = df.iloc[idx]
    st.info(f"FIDO {idx+1}/{total}")

    # --- AI suggestion for Brand/Category/Description ---
    prompt = f"""
    This is a FIDO data row for data cleanliness review.
    Brand: {row.get('brand','')}
    UPC: {row.get('UPC','')}
    Description: {row.get('description','')}
    Category: {row.get('category','')}
    IS_DELETED: {row.get('IS_DELETED','')}
    Is Brand ID Null?: {row.get('Is Brand ID Null?','')}

    Tasks:
    - If this does NOT belong to the brand, suggest "REMOVE".
    - Suggest corrected brand, category, description (if needed).
    - Otherwise suggest 'No Change'.

    Output as JSON:
    {{
        "Action": "...", "Updated Brand": "...", "Updated Category": "...", "Updated Description": "...", "Reason": "..."
    }}
    """
    with st.spinner("Getting AI suggestion..."):
        try:
            ai_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}]
            )
            suggestion = ai_response['choices'][0]['message']['content']
            import json
            suggestion_json = json.loads(suggestion)
        except Exception as e:
            suggestion_json = {"Action":"No Change","Updated Brand":"","Updated Category":"","Updated Description":"","Reason":f"AI error: {e}"}

    # Display data & suggestion
    st.write("Row Data:", row.to_dict())
    st.write("AI Suggestion:", suggestion_json)

    # Review UI
    action = st.selectbox("Action", ["KEEP", "REMOVE", "EDIT"], index=0 if suggestion_json["Action"].upper()=="NO CHANGE" else (1 if suggestion_json["Action"].upper()=="REMOVE" else 2))
    updated_brand = st.text_input("Updated Brand", suggestion_json.get("Updated Brand",""))
    updated_category = st.text_input("Updated Category", suggestion_json.get("Updated Category",""))
    updated_desc = st.text_input("Updated Description", suggestion_json.get("Updated Description",""))
    reason = st.text_area("Reason/Notes", suggestion_json.get("Reason",""))

    if st.button("Approve and Next"):
        # Time tracking, edits tracking
        if "start_time" in project and project["start_time"]:
            t = time.time() - project["start_time"]
            project["stats"]["avg_time"] += t
        # Edit tracking
        if updated_brand and updated_brand != row.get('brand',''):
            project["stats"]["brand_edits"] += 1
        if updated_category and updated_category != row.get('category',''):
            project["stats"]["cat_edits"] += 1
        if updated_desc and updated_desc != row.get('description',''):
            project["stats"]["desc_edits"] += 1
        # Save review
        review_row = dict(row)
        review_row.update({
            "Action": action,
            "Updated Brand": updated_brand,
            "Updated Category": updated_category,
            "Updated Description": updated_desc,
            "Reason": reason,
            "Reviewed By": st.session_state.user_email,
            "Review Time (sec)": round(t if "t" in locals() else 0, 2)
        })
        project["review_data"].append(review_row)
        project["start_time"] = time.time()  # reset for next FIDO
        st.experimental_rerun()

    if st.button("Quit Review"):
        st.session_state.current_review = None
        st.experimental_rerun()

# --- MAIN APP LOGIC ---
if "user_type" not in st.session_state:
    login_page()
elif st.session_state.user_type == "admin":
    admin_dashboard()
else:
    reviewer_dashboard()
