# PostgreSQL Setup for SMOKi Sensor Data

## Installation

1. Install PostgreSQL on your system
2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file based on `.env.example` and update with your database credentials

4. Create the database:
```sql
CREATE DATABASE smoki_db;
```

## Usage

```python
from postgre.database import init_db_pool, insert_sensor_data, get_latest_sensor_data

# Initialize database connection pool
init_db_pool()

# Insert sensor data
insert_sensor_data(
    temperature=25.5,
    humidity=60.2,
    vocs=150.0,
    nitrogen_dioxide=0.05,
    carbon_monoxide=0.8,
    pm25=12.5,
    pm10=18.3
)

# Get latest 10 readings
latest_data = get_latest_sensor_data(limit=10)
print(latest_data)
```

## Database Schema

### sensor_data table
- `id`: Serial primary key
- `timestamp`: Timestamp of the reading (auto-generated)
- `temperature`: Temperature in °C
- `humidity`: Humidity in %
- `vocs`: Volatile Organic Compounds in kΩ
- `nitrogen_dioxide`: Nitrogen Dioxide in PPM
- `carbon_monoxide`: Carbon Monoxide in PPM
- `pm25`: Particulate Matter 2.5 in µg/m³
- `pm10`: Particulate Matter 10 in µg/m³
- `created_at`: Record creation timestamp
