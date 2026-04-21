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
    result = conn.execute(text('UPDATE facilities SET capacity = NULL WHERE capacity = -1'))
    conn.commit()
    print(f'Updated {result.rowcount} rows locally')