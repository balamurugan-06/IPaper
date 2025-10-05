import os
import psycopg2
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# load your .env file that contains DATABASE_URL
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Change these values to your admin credentials
username = "admin"
raw_password = "Admin@123"

# Hash the password for security
hashed_password = generate_password_hash(raw_password)

# Insert into PostgreSQL
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
cur = conn.cursor()
cur.execute("""
    INSERT INTO AdminDatabase (Username, Password)
    VALUES (%s, %s)
    ON CONFLICT (Username) DO UPDATE SET Password = EXCLUDED.Password;
""", (username, hashed_password))
conn.commit()
cur.close()
conn.close()

print(f"✅ Admin '{username}' added successfully.")
