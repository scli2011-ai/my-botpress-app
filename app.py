import streamlit as st
import requests
import time
from supabase import create_client, Client

# --- 1. INITIALIZE SUPABASE ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- 2. SETUP BOTPRESS CHAT API DETAILS ---
raw_webhook_id = st.secrets.get("BOTPRESS_WEBHOOK_ID", "")
WEBHOOK_ID = raw_webhook_id.split("/")[-1].strip() 
BASE_URL = f"https://chat.botpress.cloud/{WEBHOOK_ID}"

def init_botpress_session():
    """Initializes a new user and conversation in Botpress."""
    try:
        user_res = requests.post(f"{BASE_URL}/users", json={})
        if user_res.status_code in [200, 201]:
            user_data = user_res.json()
            st.session_state.bp_user_key = user_data.get("key")
            st.session_state.bp_user_id = user_data.get("user", {}).get("id")
            
            if st.session_state.bp_user_key:
                headers = {"x-user-key": st.session_state.bp_user_key}
                conv_res = requests.post(f"{BASE_URL}/conversations", headers=headers, json={})
                if conv_res.status_code in [200, 201]:
                    st.session_state.bp_conversation_id = conv_res.json().get("conversation", {}).get("id")
    except Exception as e:
        st.error(f"Error connecting to Botpress: {e}")

# --- 3. SESSION STATE SETUP ---
if "user" not in st.session_state:
    st.session_state.user = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "bp_user_id" not in st.session_state:
    st.session_state.bp_user_id = None
if "bp_user_key" not in st.session_state:
    st.session_state.bp_user_key = None
if "bp_conversation_id" not in st.session_state:
    st.session_state.bp_conversation_id = None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("Einstein Junior App")
    if st.session_state.user:
        st.success(f"Logged in as: {st.session_state.user.email}")
        
        if st.button("Log Out"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.session_state.messages = []
            st.session_state.bp_user_id = None
            st.session_state.bp_user_key = None
            st.session_state.bp_conversation_id = None
            st.rerun()
    else:
        st.warning("You are not logged in.")

# --- 5. MAIN APP LOGIC ---
st.title("Welcome to the Future Science Classroom 👨‍🏫")

# --- UI: Login / Signup (Supabase) ---
if not st.session_state.user:
    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        st.header("Login")
        login_email = st.text_input("Email", key="login_email")
        login_password = st.text_input("Password", type="password", key="login_password", autocomplete="off")
        
        if st.button("Login"):
            try:
                response = supabase.auth.sign_in_with_password({
                    "email": login_email, 
                    "password": login_password
                })
                if response.user:
                    st.session_state.user = response.user
                    init_botpress_session() # Initialize Botpress on login
                    st.success("Login successful!")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab2:
        st.header("Create an Account")
        
        signup_name = st.text_input("Full Name", key="signup_name")
        signup_age = st.number_input("Age", min_value=1, max_value=120, step=1, value=18, key="signup_age")
        signup_gender = st.selectbox("Gender", ["Select...", "Male", "Female", "Non-binary", "Prefer not to say"], key="signup_gender")
        
        signup_email = st.text_input("Email", key="signup_email")
        signup_password = st.text_input("Password", type="password", key="signup_password", autocomplete="off")
        
        if st.button("Sign Up"):
            if not signup_name.strip():
                st.error("Please enter your full name.")
            elif signup_gender == "Select...":
                st.error("Please select a gender.")
            elif not signup_email or not signup_password:
                st.error("Please enter an email and password.")
            else:
                try:
                    response = supabase.auth.sign_up({
                        "email": signup_email, 
                        "password": signup_password
                    })
                    
                    if response.user:
                        st.success("Auth account created successfully! Saving profile data...")
                        try:
                            # Strictly matching your Supabase schema
                            supabase.table("participants").insert({
                                "participant_id": response.user.id,
                                "email": signup_email,
                                "name": signup_name,
                                "age": int(signup_age),
                                "gender": signup_gender
                            }).execute()
                            
                            st.success("User successfully added! You can now log in.")
                        except Exception as db_error:
                            st.error(f"Database Error: Could not save to participants table. Details: {db_error}")
                            
                except Exception as auth_error:
                    st.error(f"Auth Error: Could not create account. Details: {auth_error}")

# --- UI: Chat Interface (Botpress) ---
else:
    st.subheader("👨‍🏫 I am Einstein Junior, your science teacher!")
    
    # Ensure Botpress is initialized if user refreshed the page
    if not st.session_state.bp_user_key or not st.session_state.bp_conversation_id:
        init_botpress_session()
        
    if not st.session_state.bp_user_key or not st.session_state.bp_conversation_id:
        st.error("Botpress credentials missing. Please check your webhook ID or connection.")
    else:
        # Display Chat History
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Chat Input & Message Handling
        if prompt := st.chat_input("Type your message here..."):
            
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            headers = {
                "x-user-key": st.session_state.bp_user_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "conversationId": st.session_state.bp_conversation_id,
                "payload": {
                    "type": "text",
                    "text": prompt
                }
            }
            
            try:
                post_url = f"{BASE_URL}/messages"
                response = requests.post(post_url, json=payload, headers=headers)
                
                if response.status_code == 200:
                    get_url = f"{BASE_URL}/conversations/{st.session_state.bp_conversation_id}/messages"
                    bot_replied = False
                    latest_bot_reply = ""
                    
                    with st.spinner("Einstein Junior is thinking..."):
                        for _ in range(15):
                            time.sleep(1)
                            history_res = requests.get(get_url, headers=headers)
                            
                            if history_res.status_code == 200:
                                api_messages = history_res.json().get("messages", [])
                                if api_messages:
                                    latest_msg = api_messages[0]
                                    if latest_msg.get("userId") != st.session_state.bp_user_id:
                                        bot_replied = True
                                        latest_bot_reply = latest_msg["payload"].get("text", "")
                                        
                                        with st.chat_message("assistant"):
                                            st.markdown(latest_bot_reply)
                                        st.session_state.messages.append({"role": "assistant", "content": latest_bot_reply})
                                        break
                                        
                    if bot_replied:
                        # Save the interaction to the Supabase study_logs table
                        try:
                            supabase.table("study_logs").insert({
                                "participant_id": st.session_state.user.id,
                                "user_query": prompt,
                                "bot_response": latest_bot_reply
                            }).execute()
                        except Exception as db_log_error:
                            st.error(f"Failed to save log to database: {db_log_error}")
                    else:
                        st.warning("The bot took too long to reply. Try sending another message.")
                else:
                    st.error(f"Failed to send message: {response.text}")
                    
            except Exception as e:
                st.error(f"Error communicating with Botpress: {e}")