from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
url = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@localhost:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)
engine = create_engine(url)

with engine.connect() as conn:
    n = conn.execute(text("SELECT COUNT(*) FROM facilities WHERE capacity = -1")).scalar()
    print(f"Remaining -1 values: {n}")
    
    n2 = conn.execute(text("SELECT COUNT(*) FROM facilities WHERE capacity IS NULL AND type = 'shelter'")).scalar()
    print(f"Shelters with NULL capacity: {n2}")
    
    n3 = conn.execute(text("SELECT COUNT(*) FROM facilities WHERE capacity > 0 AND type = 'shelter'")).scalar()
    print(f"Shelters with valid capacity: {n3}")