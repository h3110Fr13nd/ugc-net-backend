import asyncio
import json
import sys
import os
from uuid import UUID
from difflib import SequenceMatcher
from sqlalchemy import select, delete

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import AsyncSessionLocal
from app.db.models import Taxonomy, Question, QuestionTaxonomy

# Load taxonomy
with open('taxonomy.json', 'r') as f:
    taxonomy_data = json.load(f)

# Build all valid paths from taxonomy
def flatten_taxonomy(node, parent_path="", paths=None):
    if paths is None:
        paths = []
    
    current_name = node.get("name", "")
    if parent_path:
        full_path = f"{parent_path} > {current_name}"
    else:
        full_path = current_name
        
    paths.append(full_path)
    
    for child in node.get("children", []):
        flatten_taxonomy(child, full_path, paths)
        
    return paths

valid_paths = []
for item in taxonomy_data.get("syllabus", []):
    valid_paths.extend(flatten_taxonomy(item))

print(f"Loaded {len(valid_paths)} valid taxonomy paths")

# Define manual mappings for known mismatches
MANUAL_MAPPINGS = {
    "General Paper on Teaching & Research Aptitude (Paper I) > Unit-III: Comprehension > A passage of text be given. Questions be asked from the passage to be answered": 
        "General Paper on Teaching & Research Aptitude (Paper I) > Unit-III: Comprehension > A passage of text be given. Questions be asked from the passage to be answered.",
    
    "Computer Science and Applications (Paper II) > Unit-9: Data Communication and Computer Networks > Network Security > Cryptography as a Security Tool":
        "Computer Science and Applications (Paper II) > Unit-9: Data Communication and Computer Networks > Network Security",
    
    "Computer Science and Applications (Paper II) > Unit-9: Data Communication and Computer Networks > Network Security > Cryptography and Steganography":
        "Computer Science and Applications (Paper II) > Unit-9: Data Communication and Computer Networks > Network Security",
    
    "Computer Science and Applications (Paper II) > Unit-9: Data Communication and Computer Networks > Mobile Technology > Mobile Communication Protocol":
        "Computer Science and Applications (Paper II) > Unit-9: Data Communication and Computer Networks > Mobile Technology",
    
    "General Paper on Teaching & Research Aptitude (Paper I) > Unit-V: Mathematical Reasoning and Aptitude > Counting, Mathematical Induction and Discrete Probability > Basics of Counting":
        "General Paper on Teaching & Research Aptitude (Paper I) > Unit-V: Mathematical Reasoning and Aptitude > Counting, Mathematical Induction and Discrete Probability",
    
    "General Paper on Teaching & Research Aptitude (Paper I) > Unit-9: Data Communication and Computer Networks > Network Security":
        "General Paper on Teaching & Research Aptitude (Paper I) > Unit-IX: People, Development and Environment",
    
    "General Paper on Teaching & Research Aptitude (Paper I) > Unit-V: Mathematical Reasoning and Aptitude > Counting, Mathematical Induction and Discrete Probability > Permutations and Combinations":
        "General Paper on Teaching & Research Aptitude (Paper I) > Unit-V: Mathematical Reasoning and Aptitude > Counting, Mathematical Induction and Discrete Probability",
    
    "Computer Science and Applications (Paper II) > Unit-4: Database Management Systems > Data Modeling > Relational Database Schemas":
        "Computer Science and Applications (Paper II) > Unit-4: Database Management Systems > Data Modeling > Relational Model",
}

def find_best_match(missing_path):
    # Check manual mappings first
    if missing_path in MANUAL_MAPPINGS:
        return MANUAL_MAPPINGS[missing_path]
    
    # Try fuzzy matching
    best_match = None
    best_ratio = 0
    
    for valid_path in valid_paths:
        ratio = SequenceMatcher(None, missing_path.lower(), valid_path.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = valid_path
    
    if best_ratio > 0.9:  # 90% similarity threshold
        return best_match
    
    return None

async def fix_taxonomy_links():
    async with AsyncSessionLocal() as session:
        # Build path -> taxonomy_id map
        stmt = select(Taxonomy)
        result = await session.execute(stmt)
        all_taxonomy = result.scalars().all()
        
        path_to_id = {}
        for tax in all_taxonomy:
            # Reconstruct path
            parts = []
            current = tax
            while current:
                parts.insert(0, current.name)
                if current.parent_id:
                    parent_stmt = select(Taxonomy).where(Taxonomy.id == current.parent_id)
                    parent_result = await session.execute(parent_stmt)
                    current = parent_result.scalars().first()
                else:
                    current = None
            
            path = " > ".join(parts)
            path_to_id[path] = tax.id
        
        print(f"Built path->ID map with {len(path_to_id)} entries")
        
        # Load classified questions
        with open('../tempnet/classified_questions.json', 'r') as f:
            questions = json.load(f)
        
        # Get all valid question IDs from database
        q_stmt = select(Question.id)
        q_result = await session.execute(q_stmt)
        valid_question_ids = {str(qid) for (qid,) in q_result.all()}
        print(f"Found {len(valid_question_ids)} questions in database")
        
        # Find questions with missing paths
        fixes_needed = []
        for q in questions:
            q_id = q["id"]
            # Skip if question doesn't exist in DB
            if q_id not in valid_question_ids:
                continue
                
            for path in q.get("taxonomy_paths", []):
                if path not in path_to_id:
                    best_match = find_best_match(path)
                    if best_match:
                        print(f"  Mapping: '{path}' -> '{best_match}'")
                        if best_match in path_to_id:
                            fixes_needed.append({
                                "question_id": q_id,
                                "missing_path": path,
                                "matched_path": best_match,
                                "taxonomy_id": path_to_id[best_match]
                            })
                        else:
                            print(f"    WARNING: Best match not in path_to_id!")
        
        print(f"\nFound {len(fixes_needed)} links to fix")
        
        # Apply fixes
        fixed_count = 0
        for fix in fixes_needed:
            # Check if link already exists
            check_stmt = select(QuestionTaxonomy).where(
                QuestionTaxonomy.question_id == UUID(fix["question_id"]),
                QuestionTaxonomy.taxonomy_id == fix["taxonomy_id"]
            )
            check_result = await session.execute(check_stmt)
            existing = check_result.scalars().first()
            
            if not existing:
                new_link = QuestionTaxonomy(                                                                                                                                                                                                                                                                                                        
                    question_id=UUID(fix["question_id"]),
                    taxonomy_id=fix["taxonomy_id"]
                )
                session.add(new_link)
                fixed_count += 1
                print(f"  Fixed: {fix['missing_path']} -> {fix['matched_path']}")
        
        await session.commit()
        print(f"\nAdded {fixed_count} new taxonomy links")

if __name__ == "__main__":
    asyncio.run(fix_taxonomy_links())
