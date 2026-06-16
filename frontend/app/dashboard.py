import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta


# Page configuration
st.set_page_config(page_title="Weather Analytics Dashboard", layout="wide")
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
    # 1. Create a dictionary mapping human-readable city names to their short string IDs
    # E.g., {"New York": "ny", "Tokyo": "tk", "Manila": "mnl"}
    location_map = {loc["name"]: loc["id"] for loc in supported_locations}

    # 2. Feed the human-readable names as choices to the selectbox dropdown
    selected_name = st.sidebar.selectbox(
        "Select Location",
        options=list(location_map.keys())
    )

    # 3. Resolve the clean lower-case tracking code ID to pass to your weather endpoints
    # Will evaluate as "ny", "tk", or "mnl"
    location_id = location_map[selected_name]
else:
    # Safe fallback interface layout if the backend server is temporarily unreachable
    st.sidebar.warning("Using fallback static location mapping...")
    selected_name = st.sidebar.selectbox("Select Location", ["Manila"])
    location_id = "mnl"


# Default to the last 30 days
today = date.today()
default_start = today - timedelta(days=30)

start_date = st.sidebar.date_input("Start Date", default_start)
end_date = st.sidebar.date_input("End Date", today)

threshold = st.sidebar.slider(
    "IQR Anomaly Threshold (Factor)", 1.0, 3.0, 1.5, 0.1)

# Ensure date validation
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

    # 1. Fetch raw data
    raw_res = requests.get(f"{BACKEND_URL}/weather-data", params=params)
    # 2. Fetch anomalies
    anom_params = {**params, "threshold": iqr_factor}
    anom_res = requests.get(
        f"{BACKEND_URL}/weather-data/anomalies", params=anom_params)

    if raw_res.status_code == 200 and anom_res.status_code == 200:
        return raw_res.json(), anom_res.json()
    return None, None


raw_data, anomaly_data = fetch_weather_and_anomalies(
    location_id, start_date, end_date, threshold)

# ==========================================
# VISUALIZATION & DATA RENDERING
# ==========================================
if raw_data and anomaly_data:
    # Convert hourly data payload to pandas DataFrame
    df = pd.DataFrame(raw_data["data"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Extract anomaly timestamps
    wind_anoms = pd.DataFrame(anomaly_data["wind_speed_anomalies"])
    rad_anoms = pd.DataFrame(anomaly_data["radiation_anomalies"])

    if not wind_anoms.empty:
        wind_anoms["timestamp"] = pd.to_datetime(wind_anoms["timestamp"])
    if not rad_anoms.empty:
        rad_anoms["timestamp"] = pd.to_datetime(rad_anoms["timestamp"])

    # Create layout tabs
    tab1, tab2 = st.tabs(
        ["📊 Time-Series & Anomalies", "💬 AI Weather Assistant"])

    with tab1:
        # Metric KPI cards
        col1, col2 = st.columns(2)
        col1.metric("Max Wind Speed", f"{df['wind_speed'].max():.1f} km/h")
        col2.metric("Max Solar Radiation", f"{df['radiation'].max():.1f} W/m²")

        # --- CHART 1: Wind Speed ---
        st.subheader("Wind Speed Time-Series")
        fig_wind = go.Figure()
        # Raw Data Line
        fig_wind.add_trace(go.Scatter(
            x=df["timestamp"], y=df["wind_speed"], name="Wind Speed (km/h)", line=dict(color='royalblue')))
        # Anomaly Scatter Flags
        if not wind_anoms.empty:
            fig_wind.add_trace(go.Scatter(
                x=wind_anoms["timestamp"], y=wind_anoms["value"],
                mode='markers', name='IQR Anomaly',
                marker=dict(color='crimson', size=10, symbol='x')
            ))
        fig_wind.update_layout(
            xaxis_title="Timestamp", yaxis_title="km/h", margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_wind, use_container_width=True)

        # --- CHART 2: Solar Radiation ---
        st.subheader("Shortwave Solar Radiation Time-Series")
        fig_rad = go.Figure()
        # Raw Data Line
        fig_rad.add_trace(go.Scatter(
            x=df["timestamp"], y=df["radiation"], name="Radiation (W/m²)", line=dict(color='orange')))
        # Anomaly Scatter Flags
        if not rad_anoms.empty:
            fig_rad.add_trace(go.Scatter(
                x=rad_anoms["timestamp"], y=rad_anoms["value"],
                mode='markers', name='IQR Anomaly',
                marker=dict(color='crimson', size=10, symbol='x')
            ))
        fig_rad.update_layout(
            xaxis_title="Timestamp", yaxis_title="W/m²", margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_rad, use_container_width=True)

    with tab2:
        # ==========================================
        # AI AGENT STREAMING INTERFACE
        # ==========================================
        st.subheader("Chat with your Weather Data")

        # Maintain local session chat history memory
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Render previous messages
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Capture user chat input
        if user_query := st.chat_input("Ask a question about the weather data..."):
            with st.chat_message("user"):
                st.markdown(user_query)
            st.session_state.messages.append(
                {"role": "user", "content": user_query})

            # Stream response directly from the FastAPI streaming endpoint
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                full_response = ""

                try:
                    res = requests.post(
                        f"{BACKEND_URL}/chat",
                        json={"message": user_query},
                        stream=True
                    )

                    # Read the chunks as they stream in from the server
                    for chunk in res.iter_content(chunk_size=None, decode_unicode=True):
                        if chunk:
                            full_response += chunk
                            response_placeholder.markdown(full_response + "▌")

                    response_placeholder.markdown(full_response)
                except Exception as e:
                    st.error(f"Failed to communicate with AI agent: {e}")
                    full_response = "Sorry, I am having trouble connecting to my brain right now."
                    response_placeholder.markdown(full_response)

            st.session_state.messages.append(
                {"role": "assistant", "content": full_response})
else:
    st.error(
        "Could not fetch data from the FastAPI microservice backend. "
        f"Ensure your backend server is active at {BACKEND_URL}.")
