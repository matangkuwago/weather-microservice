import json
import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config import settings


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


# Cache the city list for 10 minutes
@st.cache_data(ttl=settings.TTL_LOCATIONS)
def fetch_supported_locations():
    """Queries the FastAPI endpoint to pull current valid metadata locations."""
    try:
        response = requests.get(f"{settings.BACKEND_URL}/locations")
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
    selected_location = st.sidebar.selectbox(
        "Select Location",
        options=list(location_map.keys())
    )
    location_id = location_map[selected_location]
else:
    st.sidebar.warning("Using fallback static location mapping...")
    selected_location = st.sidebar.selectbox("Select Location", ["Manila"])
    location_id = "mnl"

start_date = st.sidebar.date_input(
    "Start Date",
    value=settings.DEFAULT_START_DATE
)
end_date = st.sidebar.date_input(
    "End Date",
    value=settings.DEFAULT_END_DATE,
)

threshold = st.sidebar.slider(
    label="IQR Anomaly Threshold (Factor)",
    min_value=settings.IQR_MIN,
    max_value=settings.IQR_MAX,
    value=settings.IQR_DEFAULT_VALUE,
    step=settings.IQR_STEP
)

if start_date > end_date:
    st.sidebar.error("Error: Start date must be before end date.")

# ==========================================
# FETCH DATA FROM BACKEND
# ==========================================


# Set cache to prevent aggressive refetches
@st.cache_data(ttl=settings.TTL_WEATHER_DATA)
def fetch_weather_and_anomalies(loc, start, end, iqr_factor):
    params = {
        "location_id": loc,
        "start_date": str(start),
        "end_date": str(end)
    }
    raw_res = requests.get(
        f"{settings.BACKEND_URL}/weather-data", params=params)
    anom_params = {**params, "threshold": iqr_factor}
    anom_res = requests.get(
        f"{settings.BACKEND_URL}/weather-data/anomalies", params=anom_params)

    if raw_res.status_code == 200 and anom_res.status_code == 200:
        return raw_res.json(), anom_res.json()
    return None, None


raw_data, anomaly_data = fetch_weather_and_anomalies(
    location_id, start_date, end_date, threshold)

# ==========================================
# VISUALIZATION & DATA RENDERING (Unified Single Column)
# ==========================================
if raw_data and anomaly_data:
    # convert hourly data payload to pandas DataFrame
    df = pd.DataFrame(raw_data["data"])

    if df.empty:
        st.warning(
            f"⚠️ No weather records found for {selected_location} "
            f"between {start_date} and {end_date}. "
            "Please select a different date range or wait for the background sync task to fetch it."
        )
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        wind_anoms = pd.DataFrame(anomaly_data["wind_speed_anomalies"])
        rad_anoms = pd.DataFrame(anomaly_data["radiation_anomalies"])

        if not wind_anoms.empty:
            wind_anoms["timestamp"] = pd.to_datetime(wind_anoms["timestamp"])
        if not rad_anoms.empty:
            rad_anoms["timestamp"] = pd.to_datetime(rad_anoms["timestamp"])

        # ------------------------------------------
        # SECTION 1: METRICS & TIME-SERIES CHARTS
        # ------------------------------------------
        st.subheader(f"📊 Analytics Summary for {selected_location}")

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
        fig_wind.update_layout(xaxis_title="Timestamp (UTC)", yaxis_title="km/h",
                               height=320, margin=dict(l=10, r=10, t=10, b=10))
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
        fig_rad.update_layout(xaxis_title="Timestamp (UTC)", yaxis_title="W/m²",
                              height=320, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_rad, use_container_width=True)

    # ------------------------------------------
    # SECTION 2: LIVE AI CHAT ASSISTANT
    # ------------------------------------------
    # Keeping the chat assistant active below the graphs so users can still
    # converse with the model even if the primary charts are empty.
    st.markdown("---")
    st.subheader("💬 AI Weather Assistant")
    st.write("Ask questions about anomalies, historical trends, or math summaries.")

    chat_container = st.container(height=450)

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
                        f"{settings.BACKEND_URL}/chat", json={"message": user_query}, stream=True)

                    for chunk in res.iter_content(chunk_size=None, decode_unicode=True):
                        if chunk:
                            full_raw_response += chunk

                            try:
                                parsed = json.loads(full_raw_response)
                                display_text = parsed.get(
                                    "reply", full_raw_response)
                            except json.JSONDecodeError:
                                display_text = full_raw_response

                            response_placeholder.markdown(display_text + "▌")

                    try:
                        final_parsed = json.loads(full_raw_response)
                        clean_reply = final_parsed.get(
                            "reply", full_raw_response)
                    except json.JSONDecodeError:
                        clean_reply = full_raw_response

                    response_placeholder.markdown(clean_reply)
                except Exception as e:
                    st.error(f"Failed to communicate with AI agent: {e}")
                    clean_reply = "Sorry, I am having trouble connecting to my brain right now."
                    response_placeholder.markdown(clean_reply)

        st.session_state.messages.append(
            {"role": "assistant", "content": clean_reply})
