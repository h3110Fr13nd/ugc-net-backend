import argparse
import json
import os
import uuid
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure the backend project root is on sys.path so `import app` works
# when running this script directly (python scripts/taxonomy-seeders.py)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.models import Base, Taxonomy # Import your Base and Taxonomy model

# --- CONFIGURATION ---
# Read DB URL and JSON path from environment for flexibility, fall back to repo defaults
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ugc")
# Change this to the new file name (can still be overridden via SYLLABUS_JSON_PATH)
JSON_FILE_PATH = os.getenv("SYLLABUS_JSON_PATH", "taxonomy.json")
# ---------------------

# Note: we delay creating the SQLAlchemy engine/session until main() so running
# the script in --dry-run mode doesn't attempt a DB connection (which avoids
# issues with asyncpg/greenlet when the URL includes +asyncpg).
engine = None
SessionLocal = None

def create_db_and_tables():
    """
    Creates all tables defined in the Base metadata.
    This is useful for a fresh setup.
    """
    Base.metadata.create_all(bind=engine)
    print("Tables created (if they didn't exist).")

def clear_taxonomy_data(session):
    """
    Deletes all existing data from the Taxonomy table to avoid duplicates.
    Be careful running this on a production DB!
    """
    print("Clearing existing taxonomy data...")
    session.query(Taxonomy).delete()
    session.commit()
    print("Data cleared.")

def insert_node(session, node_data, parent_node=None):
    """
    Recursively inserts a taxonomy node and its children into the database.
    
    `node_data` is the dict for the current node (e.g., {"name": ..., "node_type": ...})
    `parent_node` is the SQLAlchemy Taxonomy object of the parent.
    """
    
    # Check for a missing node_type, which may appear in some JSON nodes
    node_type = node_data.get('node_type')
    if not node_type:
        # Default to 'subtopic' if missing, or log a warning for visibility
        print(f"Warning: Node '{node_data.get('name', '<unknown>')}' missing 'node_type'. Defaulting to 'subtopic'.")
        node_type = 'subtopic'

    # 1. Create the new Taxonomy object
    new_node = Taxonomy(
        # Generate a UUID in the script so we can use it for the path
        id=uuid.uuid4(),
        name=node_data['name'],
        node_type=node_type,
        parent_id=parent_node.id if parent_node else None
    )
    
    # 2. Generate the materialized 'path'
    # This path is a simple dot-separated string of UUIDs.
    # e.g., "paper_id.unit_id.topic_id.subtopic_id"
    if parent_node:
        new_node.path = f"{parent_node.path}.{str(new_node.id)}"
    else:
        new_node.path = str(new_node.id)
        
    # 3. Add the new node to the session
    session.add(new_node)
    
    # 4. Recursively insert children, passing this new_node as the parent
    if 'children' in node_data and node_data['children']:
        for child_data in node_data['children']:
            insert_node(session, child_data, parent_node=new_node)

def main():
    """
    Main function to run the seeding process.
    """
    parser = argparse.ArgumentParser(description="Seed taxonomy JSON into the DB")
    parser.add_argument("--dry-run", action="store_true", help="Parse JSON and show summary without writing to DB")
    args = parser.parse_args()

    # If dry-run, just validate and summarize the JSON without touching DB.
    if args.dry_run:
        try:
            with open(JSON_FILE_PATH, 'r') as f:
                data = json.load(f)
            syllabus_papers = data.get('syllabus', [])
            print(f"Dry-run: found {len(syllabus_papers)} top-level papers in {JSON_FILE_PATH}")
            return
        except FileNotFoundError:
            print(f"Dry-run: JSON file not found at {JSON_FILE_PATH}")
            return

    # Not a dry-run: create engine and session factory now
    global engine, SessionLocal
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Optional: Create tables if they don't exist
    create_db_and_tables()

    # Get a session
    session = SessionLocal()
    
    try:
        # Optional: Clear old data to prevent errors on re-run
        # Comment this out if you want to add to existing data
        clear_taxonomy_data(session)

        # 1. Load the JSON data
        with open(JSON_FILE_PATH, 'r') as f:
            data = json.load(f)
        
        syllabus_papers = data.get('syllabus', [])
        
        if not syllabus_papers:
            print("No 'syllabus' key found in JSON. Exiting.")
            return

        print(f"Found {len(syllabus_papers)} papers to insert...")
        
        # 2. Start the recursive insertion for each top-level paper
        for paper_data in syllabus_papers:
            print(f"Inserting paper: {paper_data['name']}")
            insert_node(session, paper_data, parent_node=None)
            
        # 3. Commit the entire transaction
        print("Committing all changes to the database...")
        session.commit()
        print("✅ Syllabus successfully seeded to the database!")
        
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        print("Rolling back transaction.")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()