from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, UniqueConstraint


SQLALCHEMY_DATABASE_URL = "sqlite:///./data/weather.db"

engine = create_engine(
    # connect_args is needed only for SQLite to allow multi-threading in FastAPI
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    '''FastAPI dependency to yield database sessions'''
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class WeatherData(Base):
    __tablename__ = "weather_data"

    id = Column(Integer, primary_key=True, index=True)
    # location_id should store keys in PREDEFINED_LOCATIONS
    location_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    wind_speed = Column(Float, nullable=False)
    radiation = Column(Float, nullable=False)

    # Enforce uniqueness per city per hour
    __table_args__ = (
        UniqueConstraint('location_id', 'timestamp',
                         name='_location_timestamp_uc'),
    )
