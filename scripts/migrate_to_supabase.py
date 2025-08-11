import os
from dotenv import load_dotenv
import sqlite3
from supabase import create_client, Client

load_dotenv()

# --- CONFIGURATION ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SQLITE_DB_PATH = "./src/data/leveling.db"

# --- SCRIPT ---


def fetch_from_sqlite():
    """Fetches all data from the local SQLite database."""
    print("Connecting to SQLite database...")
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as con:
            con.row_factory = sqlite3.Row  # This allows accessing columns by name
            cur = con.cursor()

            print("Fetching data from 'users' table...")
            cur.execute("SELECT * FROM users")
            users_data = [dict(row) for row in cur.fetchall()]

            print("Fetching data from 'guild_settings' table...")
            cur.execute("SELECT * FROM guild_settings")
            guild_settings_data = [dict(row) for row in cur.fetchall()]

            print("Fetching data from 'daily_xp' table...")
            cur.execute("SELECT * FROM daily_xp")
            daily_xp_data = [dict(row) for row in cur.fetchall()]

        print("✅ Successfully fetched all data from SQLite.")
        return users_data, guild_settings_data, daily_xp_data
    except Exception as e:
        print(f"❌ Error fetching from SQLite: {e}")
        return None, None, None


def insert_to_supabase(users, guild_settings, daily_xp):
    """Inserts the fetched data into the Supabase tables."""
    if users is None or guild_settings is None or daily_xp is None:
        print("Skipping Supabase insert due to previous errors.")
        return

    try:
        print("Connecting to Supabase...")
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Connection successful.")

        # Upsert users data
        if users:
            print(f"Inserting {len(users)} rows into 'users' table...")
            supabase.table("users").upsert(users).execute()
        else:
            print("No data to insert for 'users'.")

        # Upsert guild_settings data
        if guild_settings:
            print(
                f"Inserting {len(guild_settings)} rows into 'guild_settings' table..."
            )
            supabase.table("guild_settings").upsert(guild_settings).execute()
        else:
            print("No data to insert for 'guild_settings'.")

        # Upsert daily_xp data
        if daily_xp:
            print(f"Inserting {len(daily_xp)} rows into 'daily_xp' table...")
            supabase.table("daily_xp").upsert(daily_xp).execute()
        else:
            print("No data to insert for 'daily_xp'.")

        print("✅ Successfully migrated all data to Supabase!")

    except Exception as e:
        print(f"❌ An error occurred during Supabase migration: {e}")


if __name__ == "__main__":
    print("--- Starting Database Migration ---")
    # 1. Fetch data from the local database
    users_data, guild_settings_data, daily_xp_data = fetch_from_sqlite()

    # 2. Insert data into the remote Supabase database
    insert_to_supabase(users_data, guild_settings_data, daily_xp_data)
    print("--- Migration Script Finished ---")
