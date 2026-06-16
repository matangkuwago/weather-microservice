import json
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

# ==========================================
# PAGE CONFIG & CSS INJECTION
# ==========================================
st.set_page_config(page_title="Weather Analytics Dashboard", layout="wide")


def apply_production_styles():
    """Removes top whitespace while keeping the sidebar toggle icon functional."""
    st.markdown(
        """
        <style>
        /* 1. Remove the huge empty vertical spacing container margin */
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 0rem !important;
        }
        
        /* 2. Make the header background transparent so it doesn't create whitespace,
              but DO NOT hide it completely so the toggle button stays interactive */
        header {
            background-color: rgba(0,0,0,0) !important;
        }

        /* 3. Force the sidebar reopen button to stay visible on top of everything */
        [data-testid="stSidebarCollapseButton"] {
            visibility: visible !important;
        }

        /* 4. Hide the Deploy button and clean up remaining elements */
        .stDeployButton {
            display: none !important;
        }
        #MainMenu, footer {
            visibility: hidden !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


apply_production_styles()
st.title("🌦️ Weather Analytics & Anomaly Dashboard")

BACKEND_URL = "http://backend:8000/v1"


@st.cache_data(ttl=600)  # Cache the city list for 10 minutes
def fetch_supported_locations():
    """Queries the FastAPI endpoint to pull current valid metadata locations."""
    try:
        response = requests.get(f"{BACKEND_URL}/locations")
        if response.status_code == 200:
            return response.json().get("locations", [])
        else:
            st.error(
                f"Failed to fetch locations. Server responded with: {response.status_code}")
            return []
    except Exception as e:
        st.error(f"Could not connect to backend location service: {e}")
        return []


supported_locations = fetch_supported_locations()

# ==========================================
# SIDEBAR CONTROLS (Filters)
# ==========================================
st.sidebar.header("Data Controls")

if supported_locations:
    location_map = {loc["name"]: loc["id"] for loc in supported_locations}
    selected_name = st.sidebar.selectbox(
        "Select Location",
        options=list(location_map.keys())
    )
    location_id = location_map[selected_name]
else:
    st.sidebar.warning("Using fallback static location mapping...")
    selected_name = st.sidebar.selectbox("Select Location", ["Manila"])
    location_id = "mnl"

# Default to the last 30 days
today = date.today()
thirty_days_ago = today - timedelta(days=30)

start_date = st.sidebar.date_input(
    "Start Date",
    value=thirty_days_ago,
    min_value=thirty_days_ago,  # Restricts user from clicking dates older than 30 days
    max_value=today             # Restricts user from clicking future dates
)
end_date = st.sidebar.date_input(
    "End Date",
    value=today,
    min_value=thirty_days_ago,  # Restricts user from clicking dates older than 30 days
    max_value=today             # Restricts user from clicking future dates
)

threshold = st.sidebar.slider(
    label="IQR Anomaly Threshold (Factor)",
    min_value=1.0,
    max_value=4.0,     # Extended upper limit for extreme outlier filtering
    value=1.5,         # Standard default Tukey outlier baseline
    step=0.1
)

if start_date > end_date:
    st.sidebar.error("Error: Start date must be before end date.")

# ==========================================
# FETCH DATA FROM BACKEND
# ==========================================


@st.cache_data(ttl=60)  # Cache for 1 minute to prevent aggressive refetches
def fetch_weather_and_anomalies(loc, start, end, iqr_factor):
    params = {
        "location_id": loc,
        "start_date": str(start),
        "end_date": str(end)
    }
    raw_res = requests.get(f"{BACKEND_URL}/weather-data", params=params)
    anom_params = {**params, "threshold": iqr_factor}
    anom_res = requests.get(
        f"{BACKEND_URL}/weather-data/anomalies", params=anom_params)

    if raw_res.status_code == 200 and anom_res.status_code == 200:
        return raw_res.json(), anom_res.json()
    return None, None


raw_data, anomaly_data = fetch_weather_and_anomalies(
    location_id, start_date, end_date, threshold)

# ==========================================
# VISUALIZATION & DATA RENDERING (Unified View)
# ==========================================
if raw_data and anomaly_data:
    df = pd.DataFrame(raw_data["data"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    wind_anoms = pd.DataFrame(anomaly_data["wind_speed_anomalies"])
    rad_anoms = pd.DataFrame(anomaly_data["radiation_anomalies"])

    if not wind_anoms.empty:
        wind_anoms["timestamp"] = pd.to_datetime(wind_anoms["timestamp"])
    if not rad_anoms.empty:
        rad_anoms["timestamp"] = pd.to_datetime(rad_anoms["timestamp"])

    # 1. Split page into 2 side-by-side columns: Charts (2/3 width) and Chat (1/3 width)
    chart_column, chat_column = st.columns([2, 1], gap="large")

    # ------------------------------------------
    # LEFT COLUMN: METRICS & TIME-SERIES CHARTS
    # ------------------------------------------
    with chart_column:
        st.subheader(f"📊 Analytics Summary for {selected_name}")

        col1, col2 = st.columns(2)
        col1.metric("Max Wind Speed", f"{df['wind_speed'].max():.1f} km/h")
        col2.metric("Max Solar Radiation", f"{df['radiation'].max():.1f} W/m²")

        # Wind Speed Chart
        st.write("#### Wind Speed Time-Series")
        fig_wind = go.Figure()
        fig_wind.add_trace(go.Scatter(
            x=df["timestamp"], y=df["wind_speed"], name="Wind Speed (km/h)", line=dict(color='royalblue')))
        if not wind_anoms.empty:
            fig_wind.add_trace(go.Scatter(
                x=wind_anoms["timestamp"], y=wind_anoms["value"],
                mode='markers', name='IQR Anomaly',
                marker=dict(color='crimson', size=10, symbol='x')
            ))
        fig_wind.update_layout(xaxis_title="Timestamp", yaxis_title="km/h",
                               height=280, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_wind, use_container_width=True)

        # Solar Radiation Chart
        st.write("#### Shortwave Solar Radiation Time-Series")
        fig_rad = go.Figure()
        fig_rad.add_trace(go.Scatter(
            x=df["timestamp"], y=df["radiation"], name="Radiation (W/m²)", line=dict(color='orange')))
        if not rad_anoms.empty:
            fig_rad.add_trace(go.Scatter(
                x=rad_anoms["timestamp"], y=rad_anoms["value"],
                mode='markers', name='IQR Anomaly',
                marker=dict(color='crimson', size=10, symbol='x')
            ))
        fig_rad.update_layout(xaxis_title="Timestamp", yaxis_title="W/m²",
                              height=280, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_rad, use_container_width=True)

    # ------------------------------------------
    # RIGHT COLUMN: LIVE AI CHAT ASSISTANT
    # ------------------------------------------
    with chat_column:
        st.subheader("💬 AI Weather Assistant")
        st.write(
            "Ask questions about anomalies, historical trends, or math summaries.")

        # Fixed scrollable container window for the chat history log
        chat_container = st.container(height=520)

        if "messages" not in st.session_state:
            st.session_state.messages = []

        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if user_query := st.chat_input("Ask a question about the weather data..."):
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(user_query)
            st.session_state.messages.append(
                {"role": "user", "content": user_query})

            with chat_container:
                with st.chat_message("assistant"):
                    response_placeholder = st.empty()
                    full_raw_response = ""
                    clean_reply = ""

                    try:
                        res = requests.post(
                            f"{BACKEND_URL}/chat", json={"message": user_query}, stream=True)

                        for chunk in res.iter_content(chunk_size=None, decode_unicode=True):
                            if chunk:
                                full_raw_response += chunk

                                # On-the-fly streaming text decoder to unwrap JSON objects progressively
                                try:
                                    parsed = json.loads(full_raw_response)
                                    display_text = parsed.get(
                                        "reply", full_raw_response)
                                except json.JSONDecodeError:
                                    display_text = full_raw_response

                                response_placeholder.markdown(
                                    display_text + "▌")

                        # Complete extraction parsing block once stream terminates
                        try:
                            final_parsed = json.loads(full_raw_response)
                            clean_reply = final_parsed.get(
                                "reply", full_raw_response)
                        except json.JSONDecodeError:
                            clean_reply = full_raw_response

                        response_placeholder.markdown(clean_reply)
                    except Exception as e:
                        st.error(f"Failed to communicate with AI agent: {e}")
                        clean_reply = "Sorry, I am having trouble connecting to the AI agent right now."
                        response_placeholder.markdown(clean_reply)

            st.session_state.messages.append(
                {"role": "assistant", "content": clean_reply})
else:
    st.error(
        f"Could not fetch data from the FastAPI microservice backend. Ensure your backend server is active at {BACKEND_URL}.")
