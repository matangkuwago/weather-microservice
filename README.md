## 🌦️ Weather Analytics & Local AI Agent Microservice

A containerized, lightweight weather analytics platform built with FastAPI and Streamlit. The system maintains a rolling database cache of the past 30 days of hourly wind speed and solar radiation data for Manila, Tokyo, and New York from the Open-Meteo Archive API. The system uses the Interquartile Range (IQR) anomaly detection pipeline and an AI Chat Assistant capable of executing backend tool calls to summarize metrics and isolate weather anomalies.

------------------------------
## 🛠️ System Architecture & Layout
The project enforces a separation of concerns, decoupling the frontend interface and backend services.

```text
weather-service/
├── docker-compose.yml       # Multi-container service orchestrator
├── backend/
│   ├── Dockerfile           # Backend container build instructions
│   ├── Dockerfile.Ollama    # Ollama container build instructions
│   ├── requirements.txt     # Package requirements for the backend
│   └── app/
│       ├── main.py          # FastAPI application server & routes
│       ├── config.py        # Settings class
│       ├── database.py      # SQLite connection & engine setup and SQLAlchemy data mapping
│       ├── schemas.py       # Pydantic validation envelopes
│       ├── tasks.py         # Data download background task
│       ├── services.py      # Local data query service
│       ├── open_meteo.py    # Module for getting data from Open-Meteo.com
│       ├── agent.py         # Module for AI Agent orchestration
└── frontend/
    ├── Dockerfile.dashboard # Streamlit isolated image layer
    ├── requirements.txt     # Package requirements for the frontend
    └── app/
        └── dashboard.py     # Side-by-side data visualization & chat UI
```

## ⏳ Data Synchronization
The microservice runs an automated background worker (sync_weather_data) on a configurable schedule (SYNC_INTERVAL_SECONDS) to clean, repair, and cache historical weather data from Open-Meteo.com into an SQLite database.

```text
[ Trigger ] ──> Purge records older than rolling history threshold (30 days)
[ Analysis] ──> Query SQLite for the latest cached timestamp to identify missing gaps
[ Request ] ──> Fetch all location data from Open-Meteo.com in a single network call
[ Cleanse ] ──> Run linear series interpolation for missing values & clip bounds
[ Write   ] ──> Filter out timestamps existing in the database and save the new updates
```

## 🔬 Anomaly Algorithmic Selection: Why IQR Instead of Z-Score?
Here is why the Interquartile Range (IQR) method works much better than a Z-score for tracking wind and solar data:

*   **Works on Real-World Weather Patterns**
    *   Z-score only works if your data is perfectly symmetrical.
    *   In reality, wind speed has sudden storm spikes and solar radiation turns completely off at night, which breaks the Z-score math.
*   **Prevents Self-Blinding**
    *   Big events like typhoons distort standard averages.
    *   This causes the Z-score boundary to pull itself upward, accidentally blinding the system to smaller, subsequent weather changes.
*   **Ignores Broken Sensors and Flukes**
    *   IQR protects your thresholds by focusing exclusively on the normal middle 50% of your data.
    *   This ensures your baseline limits aren't ruined by a single crazy sensor error or a passing storm.




------------------------------
## ⚡ Quick Start

## 1. Setup Your Configuration Matrix
Create a file named `.env` in the root directory:

```bash
# Choose between: ollama, openai, or anthropic
AI_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b

# Cloud API Tokens and models (Only required if AI_PROVIDER is set to cloud profiles)
OPENAI_API_KEY=sk-proj-xxxx...
OPENAI_MODEL=gpt-4o

ANTHROPIC_API_KEY=sk-ant-xxxx...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

## 2. Launch the Entire System Stack
Compile and trigger all three containers simultaneously from your main project folder root directory:

```bash
docker compose up --build -d
```

If `AI_PROVIDER` is set to `ollama`, the system will automatically pull and initialize the 4.7 GB Qwen model inside the docker build phase.

## 3. Verify System Infrastructure
Open your browser to start exploring:

* Interactive Dashboard: http://localhost:8501
* FastAPI API Swagger Documentation Docs: http://localhost:8000/docs

------------------------------
## 💬 Conversational Starters to Try in the Dashboard

The AI Weather Assistant understands everyday language (like 'last week'), automatically converts it into exact dates, grabs the right data for multiple cities at once, and handles all the math for you.

* “Which site had the highest average solar radiation last week?”
* “Were there any extreme wind speed anomalies detected in Manila between June 1st and June 10th? Use an IQR factor threshold of 2.5.”
* “Compare the maximum wind speed seen in Tokyo versus New York over the last 14 days.”
* “Look at the solar data for Manila over the past month. Does the radiation profile show any abnormal noon-time dropouts?”
