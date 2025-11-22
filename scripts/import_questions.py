import asyncio
import json
import os
import shutil
import sys
import csv
import re
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import AsyncSessionLocal, engine
from app.db.models import (
    Taxonomy, Question, QuestionPart, Option, OptionPart, 
    QuestionTaxonomy, Media
)

# Configuration
TAXONOMY_FILE = "taxonomy.json" # In backend/
QUESTIONS_FILE = "classified_questions.json"
MEDIA_SOURCE_DIR = "extracted_media"
MEDIA_DEST_DIR = "uploads"
YEAR_MAPPING_FILE = "year_mapping.json"

# Ensure media dest exists
os.makedirs(MEDIA_DEST_DIR, exist_ok=True)

def load_year_mapping():
    """Load the year mapping from the JSON file created by build_year_mapping.py."""
    print("Loading year mapping from file...")
    if not os.path.exists(YEAR_MAPPING_FILE):
        print(f"Warning: Year mapping file not found at {YEAR_MAPPING_FILE}")
        return {}
    
    with open(YEAR_MAPPING_FILE, 'r', encoding='utf-8') as f:
        year_map = json.load(f)
    
    # Get statistics
    years = {}
    for filename, year in year_map.items():
        years[year] = years.get(year, 0) + 1
    
    print(f"  Loaded {len(year_map)} filename-to-year mappings")
    print(f"  Years covered: {sorted(years.keys())}")
    return year_map

async def seed_taxonomy(session: AsyncSession, taxonomy_data: dict):
    print("Seeding taxonomy...")
    path_map = {} # path_string -> taxonomy_id

    async def process_node(node, parent_id=None, parent_path=""):
        name = node["name"]
        node_type = node.get("node_type", "topic")
        
        # Construct path
        current_path = f"{parent_path}.{name}" if parent_path else name
        
        # Check if exists
        stmt = select(Taxonomy).where(
            Taxonomy.name == name, 
            Taxonomy.parent_id == parent_id
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()
        
        if existing:
            tax_id = existing.id
            # print(f"  Found existing: {name}")
        else:
            tax_id = uuid4()
            new_node = Taxonomy(
                id=tax_id,
                name=name,
                node_type=node_type,
                parent_id=parent_id,
                path=current_path
            )
            session.add(new_node)
            # print(f"  Created: {name}")
        
        path_map[current_path] = tax_id
        
        # Process children
        for child in node.get("children", []):
            await process_node(child, tax_id, current_path)

    for item in taxonomy_data.get("syllabus", []):
        await process_node(item)
    
    await session.commit()
    print("Taxonomy seeded.")
    return path_map


async def create_year_taxonomy(session: AsyncSession, year_map: dict):
    """Create Year taxonomy nodes and return year -> taxonomy_id mapping."""
    print("Creating Year taxonomy...")
    year_tax_map = {}  # year -> taxonomy_id
    
    # Create or get root "Year" node
    stmt = select(Taxonomy).where(
        Taxonomy.name == "Year",
        Taxonomy.parent_id == None
    )
    result = await session.execute(stmt)
    year_root = result.scalars().first()
    
    if not year_root:
        year_root = Taxonomy(
            id=uuid4(),
            name="Year",
            node_type="root",
            parent_id=None,
            path="Year",
            description="Questions organized by year"
        )
        session.add(year_root)
        await session.flush()
        print("  Created Year root node")
    
    # Get unique years from the mapping
    unique_years = sorted(set(year_map.values()))
    
    # Create year nodes
    for year in unique_years:
        stmt = select(Taxonomy).where(
            Taxonomy.name == str(year),
            Taxonomy.parent_id == year_root.id
        )
        result = await session.execute(stmt)
        year_node = result.scalars().first()
        
        if not year_node:
            year_node = Taxonomy(
                id=uuid4(),
                name=str(year),
                node_type="year",
                parent_id=year_root.id,
                path=f"Year.{year}",
                description=f"Questions from {year}"
            )
            session.add(year_node)
            await session.flush()
            print(f"  Created year node: {year}")
        
        year_tax_map[year] = year_node.id
    
    await session.commit()
    print(f"Year taxonomy created with {len(year_tax_map)} year nodes.")
    return year_tax_map


def find_tax_id(path_map, path_str):
    """Find taxonomy ID by path string."""
    # Classifier: "A > B > C"
    # DB Path: "A.B.C"
    # Let's try to match by exact name chain
    parts = [p.strip() for p in path_str.split(">")]
    db_path_key = ".".join(parts)
    return path_map.get(db_path_key)

async def handle_media(session: AsyncSession, media_path_ref: str):
    if not media_path_ref: return None
    
    filename = os.path.basename(media_path_ref)
    source_path = os.path.join(MEDIA_SOURCE_DIR, filename)
    dest_path = os.path.join(MEDIA_DEST_DIR, filename)
    
    if not os.path.exists(source_path):
        print(f"  Warning: Media not found: {source_path}")
        return None
        
    # Copy file
    shutil.copy2(source_path, dest_path)
    
    # Create Media record
    # Check if exists first to avoid duplicates?
    stmt = select(Media).where(Media.storage_key == filename)
    result = await session.execute(stmt)
    existing = result.scalars().first()
    
    if existing:
        # Fix URL if needed (e.g. if prefix changed)
        expected_url = f"/media/files/{filename}"
        if existing.url != expected_url:
            print(f"  Fixing URL for {filename}")
            existing.url = expected_url
            session.add(existing)
            await session.flush()
        return existing.id
        
    media_id = uuid4()
    new_media = Media(
        id=media_id,
        url=f"/media/files/{filename}", # Virtual URL matching main.py mount
        storage_key=filename,
        mime_type="image/png", # Assumed
        uploaded_by=None # System upload
    )
    session.add(new_media)
    await session.flush() # Get ID
    return media_id

async def import_questions(session: AsyncSession, questions: list, path_map: dict, year_tax_map: dict, filename_year_map: dict):
    print(f"Importing {len(questions)} questions...")
    count = 0
    
    for q_data in questions:
        # Create Question
        q_id = uuid4()
        question = Question(
            id=q_id,
            title=q_data.get("title"),
            answer_type="options",
            meta_data=q_data.get("meta_data", {})
        )
        session.add(question)
        
        # Parts
        for idx, part in enumerate(q_data.get("parts", [])):
            media_id = None
            if part.get("media_path"):
                media_id = await handle_media(session, part["media_path"])
                
            q_part = QuestionPart(
                question_id=q_id,
                index=idx,
                part_type=part.get("part_type", "text"),
                content=part.get("content"),
                media_id=media_id,
                meta_data={"description": part.get("description")}
            )
            session.add(q_part)
            
        # Options
        for idx, opt in enumerate(q_data.get("options", [])):
            opt_id = uuid4()
            option = Option(
                id=opt_id,
                question_id=q_id,
                label=opt.get("label"),
                index=idx,
                is_correct=opt.get("is_correct", False)
            )
            session.add(option)
            
            for p_idx, p_part in enumerate(opt.get("parts", [])):
                media_id = None
                if p_part.get("media_path"):
                    media_id = await handle_media(session, p_part["media_path"])
                    
                o_part = OptionPart(
                    option_id=opt_id,
                    index=p_idx,
                    part_type=p_part.get("part_type", "text"),
                    content=p_part.get("content"),
                    media_id=media_id
                )
                session.add(o_part)
                
        # Taxonomy Links
        # Link to general taxonomy
        for path_str in q_data.get("taxonomy_paths", []):
            tax_id = find_tax_id(path_map, path_str)
            if tax_id:
                link = QuestionTaxonomy(
                    id=uuid4(),
                    question_id=q_id,
                    taxonomy_id=tax_id
                )
                session.add(link)
            else:
                print(f"  Warning: Taxonomy path not found: {path_str}")
        
        # Link to year taxonomy
        meta_data = q_data.get('meta_data', {})
        source_file = meta_data.get('source_file', '')
        if source_file:
            # Extract filename from path like "tmp_pdfs/code_00/J-00-14-I Set-Y.pdf"
            filename = os.path.basename(source_file)
            year = filename_year_map.get(filename)
            
            if year and year in year_tax_map:
                year_tax_id = year_tax_map[year]
                # Check if link already exists (avoid duplicates)
                stmt = select(QuestionTaxonomy).where(
                    QuestionTaxonomy.question_id == q_id,
                    QuestionTaxonomy.taxonomy_id == year_tax_id
                )
                result = await session.execute(stmt)
                existing_link = result.scalars().first()
                
                if not existing_link:
                    year_link = QuestionTaxonomy(
                        id=uuid4(),
                        question_id=q_id,
                        taxonomy_id=year_tax_id
                    )
                    session.add(year_link)
        
        count += 1
        if count % 100 == 0:
            print(f"  Imported {count}...")
            await session.commit()
            
    await session.commit()
    print(f"Finished importing {count} questions.")

from sqlalchemy import delete

async def delete_all_questions(session: AsyncSession):
    print("Deleting all existing questions...")
    # Delete dependencies first due to foreign key constraints
    print("  Deleting QuestionTaxonomy links...")
    await session.execute(delete(QuestionTaxonomy))
    
    print("  Deleting QuestionParts...")
    await session.execute(delete(QuestionPart))
    
    print("  Deleting OptionParts...")
    await session.execute(delete(OptionPart))
    
    print("  Deleting Options...")
    await session.execute(delete(Option))
    
    print("  Deleting Questions...")
    await session.execute(delete(Question))
    
    await session.commit()
    print("All questions deleted.")

async def main():
    async with AsyncSessionLocal() as session:
        # 0. Clear existing questions
        await delete_all_questions(session)

        # 1. Load Taxonomy
        with open(TAXONOMY_FILE, 'r') as f:
            taxonomy_data = json.load(f)
        path_map = await seed_taxonomy(session, taxonomy_data)
        
        # 2. Load Questions
        if not os.path.exists(QUESTIONS_FILE):
            print(f"Questions file not found: {QUESTIONS_FILE}")
            return
            
        with open(QUESTIONS_FILE, 'r') as f:
            questions = json.load(f)
        
        # 3. Load year mapping from file
        filename_year_map = load_year_mapping()
        year_tax_map = await create_year_taxonomy(session, filename_year_map)
        
        # 4. Import questions with year links
        await import_questions(session, questions, path_map, year_tax_map, filename_year_map)

if __name__ == "__main__":
    asyncio.run(main())
