from datetime import datetime, timezone
import numpy as np
import pandas as pd


def forecast_fixture():
    now=pd.Timestamp.now(tz="Africa/Nairobi")
    start=now.normalize()-pd.Timedelta(days=1)
    idx=pd.date_range(start,periods=96,freq="h")
    daylight=np.maximum(np.sin((idx.hour.to_numpy()-6)/12*np.pi),0)
    frame=pd.DataFrame({"temp_air":23.0,"relative_humidity":55.0,"pressure":84000.0,
        "wind_speed":2.0,"gust_ms":4.0,"wind_direction_deg":30.0,"cloud_pct":10.0,
        "precipitation_mm":0.0,"weather_code":1,"ghi":800*daylight,"dni":600*daylight,
        "dhi":150*daylight},index=idx)
    meta={"provider":"Test fixture","source_url":"https://open-meteo.com/en/docs",
        "retrieved_utc":datetime.now(timezone.utc).isoformat(),"current_time":now.isoformat(),
        "current":{},"cache_status":"Offline test fixture","timezone":"Africa/Nairobi"}
    return frame,meta
