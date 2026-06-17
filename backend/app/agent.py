import logging
from datetime import datetime

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.schemas import (
    PREDEFINED_LOCATIONS,
    WeatherDataPoint,
    WeatherQueryParams,
    WeatherSummary,
    AnomalyReport,
    ToolError
)
from app.services import detect_iqr_anomalies, get_cached_weather


logger = logging.getLogger("weather-agent")


def get_location_id(location_name: str) -> str:
    location_id = next(
        (k for k, v in PREDEFINED_LOCATIONS.items()
         if v["name"].lower() == location_name.lower()),
        None
    )
    return location_id


# The weather data tools the AI agent can execute

@tool
def get_weather_data(location_name: str, start_date: str, end_date: str) -> WeatherSummary | ToolError:
    """
    Fetches raw wind speed and solar radiation metrics for a given location and date range.
    - location: Must be one of the names in PREDEFINED_LOCATIONS
    - start_date: Format 'YYYY-MM-DD'
    - end_date: Format 'YYYY-MM-DD'
    """
    try:
        location_id = get_location_id(location_name)

        if not location_id:
            allowed_names = ", ".join([v["name"]
                                      for v in PREDEFINED_LOCATIONS.values()])
            return {"error": f"Location '{location_name}' is not supported. Choose from: {allowed_names}"}

        params = WeatherQueryParams(
            location_id=location_id,
            start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
            end_date=datetime.strptime(end_date, "%Y-%m-%d").date()
        )

        # Open database context session
        db: Session = SessionLocal()
        try:
            location_meta, records = get_cached_weather(params, db)

            if not records:
                location_name = location_meta["name"]
                return ToolError(error=f"No data found in the database from {start_date} to {end_date} for location '{location_name}'.")

            # Compute high-level statistical summaries to save LLM reasoning tokens
            # This prevents the AI from making simple math or averaging errors
            wind_speeds = [r.wind_speed for r in records]
            radiations = [r.radiation for r in records]

            avg_wind = sum(wind_speeds) / len(wind_speeds)
            avg_rad = sum(radiations) / len(radiations)

            # Format the unified flat response payload for the LLM Agent
            return WeatherSummary(
                location=location_meta["name"],
                location_id=location_id,
                analysis_period={"start": start_date, "end": end_date},
                summary={
                    "total_hours_retrieved": len(records),
                    "average_wind_speed_kmh": round(avg_wind, 2),
                    "max_wind_speed_kmh": round(max(wind_speeds), 2),
                    "average_solar_radiation_wm2": round(avg_rad, 2),
                    "max_solar_radiation_wm2": round(max(radiations), 2)
                },
                # Detailed time-series array mapping
                hourly_data=[
                    {
                        "timestamp": r.timestamp.isoformat(),
                        "wind_speed": r.wind_speed,
                        "radiation": r.radiation
                    }
                    for r in records
                ]
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"get_weather_data failed: {e}")
        return ToolError(error=f"Failed to retrieve data: {str(e)}")


@tool
def get_weather_anomalies(location_name: str, start_date: str, end_date: str, threshold: float = 1.5) -> AnomalyReport | ToolError:
    """
    Finds IQR anomalies for wind or solar radiation for a specific date range and location.
    - location: Must be one of the names in PREDEFINED_LOCATIONS
    - start_date: Format 'YYYY-MM-DD'
    - end_date: Format 'YYYY-MM-DD'
    """

    try:
        location_id = get_location_id(location_name)

        if not location_id:
            allowed_names = ", ".join([v["name"]
                                      for v in PREDEFINED_LOCATIONS.values()])
            return ToolError(error=f"Location '{location_name}' is not supported. "
                             f"Choose from: {allowed_names}"
                             )

        params = WeatherQueryParams(
            location_id=location_id,
            start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
            end_date=datetime.strptime(end_date, "%Y-%m-%d").date()
        )

        # Open database context session
        db: Session = SessionLocal()
        try:
            location_meta, records = get_cached_weather(params, db)

            if not records:
                location_name = location_meta["name"]
                return ToolError(error=f"No data found in the database from {start_date} to {end_date} for location '{location_name}'.")

            data_points = [WeatherDataPoint(
                timestamp=r.timestamp, wind_speed=r.wind_speed, radiation=r.radiation) for r in records]
            anomalies = detect_iqr_anomalies(data_points, factor=threshold)

            return AnomalyReport(
                location=location_meta["name"],
                location_id=location_id,
                analysis_period={"start": start_date, "end": end_date},
                method=f"IQR (threshold factor: {threshold})",
                summary={
                    "total_hours_analyzed": len(records),
                    "wind_speed_anomalies_count": len(anomalies["wind_speed"]),
                    "radiation_anomalies_count": len(anomalies["radiation"])
                },
                # Return mapped JSON-friendly lists for the AI to print out or trace
                wind_speed_anomalies=[
                    {"timestamp": item.timestamp.isoformat(
                    ), "observed_value": item.value, "limit_bound": item.bound_limit}
                    for item in anomalies["wind_speed"]
                ],
                radiation_anomalies=[
                    {"timestamp": item.timestamp.isoformat(
                    ), "observed_value": item.value, "limit_bound": item.bound_limit}
                    for item in anomalies["radiation"]
                ]
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"get_weather_anomalies failed: {e}")
        return ToolError(error=f"Failed to retrieve data: {str(e)}")


#  Build the Agent Executor Instance

def get_llm_provider():
    '''Factory to resolve the selected AI Provider'''

    if settings.AI_PROVIDER == "ollama":
        logger.info(f"Creating a ChatOllama provider.")
        return ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            temperature=settings.AI_TEMPERATURE
        )
    elif settings.AI_PROVIDER == "openai":
        logger.info(f"Creating a ChatOpenAI provider.")
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=settings.AI_TEMPERATURE,
            api_key=settings.OPENAI_API_KEY
        )
    elif settings.AI_PROVIDER == "anthropic":
        logger.info(f"Creating a ChatAnthropic provider.")
        return ChatAnthropic(
            model=settings.ANTHROPIC_MODEL,
            temperature=settings.AI_TEMPERATURE,
            api_key=settings.ANTHROPIC_API_KEY
        )
    else:
        raise ValueError(
            f"Unsupported AI Provider configured: {settings.AI_PROVIDER}")


# for caching agent instances at runtime
_cached_executor: AgentExecutor | None = None
_cached_provider_string: str | None = None


def get_weather_agent_executor() -> AgentExecutor:
    """Returns a cached AgentExecutor; reconstructs if config changes."""
    global _cached_executor, _cached_provider_string

    current_provider = str(settings.AI_PROVIDER).strip().lower()

    # return cached instance if provider hasn't changed
    if _cached_executor is not None and _cached_provider_string == current_provider:
        logger.info(
            f"Reusing cached {_cached_provider_string} AgentExecutor instance.")
        return _cached_executor

    # re-initialize only on config change or first run
    logger.info(f"Compiling new agent for provider: {current_provider}")

    tools = [get_weather_data, get_weather_anomalies]
    llm = get_llm_provider()

    locations = [k["name"] for k in PREDEFINED_LOCATIONS.values()]

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a weather microservice analytics assistant. "
            f"Today's date is {datetime.now().strftime('%Y-%m-%d')}. "
            f"You have access to tools to get weather records for {', '.join(locations)}. "
            "When users ask questions relative to time (like 'last week'), convert them to explicit YYYY-MM-DD parameters. "
            "When users ask questions about anomalies, pass the threshold factor if specified. "
            "When users ask questions about time, note that the timestamps returned by tools are in UTC. "
            "Always convert these timestamps into the user's local timezone when formulating your final response. "
            "The default multiplier threshold is 1.5, but users can scale it up to 4.0 to isolate extreme outliers. "
            "Always invoke the get_weather_data and get_weather_anomalies tools to look up information before formulating your final answer. "
            "CRITICAL RULE: You must always think and respond exclusively in English. "
            "Do not use Chinese characters, phrases, or grammar under any circumstances. Every word you output must be English."
        )),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # build the agent
    agent = create_tool_calling_agent(llm, tools, prompt)

    # update the cache
    _cached_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    _cached_provider_string = current_provider

    return _cached_executor
